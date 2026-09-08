# Decision: Unidirectional calendar sync architecture

**Status:** accepted (spec); implementation slices C1–C5 in progress  
**Live spec:** `LLM/domains/scheduling/calendar_email.md` (+ booking confirmation section in `scheduling/booking.md`)  
**What we took:** App as sole source of truth; Email A (review, no ICS) → client manage POST → Email B `REQUEST`/`SEQUENCE:0`; later Email C or staff **immediate ICS** override; `METHOD:CANCEL` + rising SEQUENCE; no inbound MIME/API client sync; SafeLinks-safe GET.  
**Dad4dogs adaptations:** Operator books, client confirms; one manage token per visit; series **confirm all** on review page while each VEVENT keeps its own manage URL; client reschedule on manage page in MVP; staff edit checkbox to skip Email C when verbally agreed.  
**What we left / wontfix:** Live Gmail calendar read for client sync; parsing ACCEPT/DECLINE replies; two-way calendar sync. Staff `/ical/` feed and parked `PendingCalendarEvent` file import unchanged.  
**Why:** Fragile two-way sync and auto-ICS on staff edit left client calendars wrong or confirmed by scanners; branded confirm page keeps consent and SEQUENCE honest.

---

# Historical proposal body
# Architecture & Implementation Plan: Unidirectional Calendar Synchronization

## 1. Executive Summary & Design Philosophy
This document specifies a resilient, unidirectional calendar synchronization workflow for the dog sitting application. 

Instead of relying on fragile two-way API syncs, OAuth permissions, or parsing incoming RFC-5545 MIME replies from third-party mail providers (Outlook, Apple Mail, Gmail), the application acts as the **single source of truth**. 

State transitions are driven exclusively via user interaction on a branded web landing page accessed through secure, tokenized links. The client's calendar application is treated strictly as a downstream consumer of `.ics` calendar updates.

---

## 2. End-to-End Workflow

```
[Customer Books / Appointment Created]
                 â”‚
                 â–¼
[Email 1: Review & Confirmation Link] (No .ics attachment)
                 â”‚
                 â–¼
[Customer Lands on Branded Management Page]
  - Reviews booking details
  - Can modify date / time inline
  - Clicks [Confirm & Add to Calendar]
                 â”‚
                 â–¼
[Database Updated: Status = CONFIRMED, ics_sequence = 0]
                 â”‚
                 â–¼
[Email 2: Confirmed Booking + .ics Attachment (METHOD:REQUEST, SEQUENCE:0)]
  - .ics contains permanent management URL in the DESCRIPTION field
                 â”‚
                 â–¼
[Customer Adds Event to Native Calendar (Outlook / Apple / Google)]
```

### Subsequent Modifications & Cancellations

```
[Customer clicks management link inside their calendar event (or logs in)]
                 â”‚
                 â–¼
[Branded Landing Page (State: CONFIRMED)]
                 â”‚
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â–¼                                    â–¼
 [Reschedule Action]                 [Cancel Action]
        â”‚                                    â”‚
 [Select new date/time]              [Confirm cancellation]
        â”‚                                    â”‚
 [ics_sequence += 1]                 [ics_sequence += 1]
 [Database updated]                  [Status = CANCELLED]
        â”‚                                    â”‚
        â–¼                                    â–¼
 [Email 3: Updated .ics]             [Email 4: Cancellation .ics]
 (METHOD:REQUEST, SEQUENCE:N)        (METHOD:CANCEL, SEQUENCE:N)
        â”‚                                    â”‚
        â–¼                                    â–¼
 [Client's calendar moves            [Client's calendar removes
  the appointment slot]               or strikes the appointment]
```

---

## 3. Detailed Step Specifications

### Step 1: Initial Booking & Link Dispatch
* **Trigger:** Customer initiates a booking or an administrator schedules an appointment.
* **Email Sent:** Clean transactional email without attachments.
  * **Subject:** *Confirm Buster's Booking with Dad 4 Dogs*
  * **Body:** Summarizes request and presents a single primary call-to-action button linking to the management portal:
    ```text
    https://app.yourdomain.com/appointments/manage?token=<SECURE_UNIQUE_TOKEN>
    ```
* **Anti-Bot Defense:** The email does not perform an immediate confirmation upon link fetch. This prevents enterprise email security tools (e.g., SafeLinks, virus scanners) from auto-confirming the slot.

### Step 2: The Branded Landing Page
* **Route:** `GET /appointments/manage?token=<token>`
* **State Behavior:**
  * **If Status == `PENDING`:**
    * Displays dog profile, service type, requested dates/times.
    * Allows immediate inline adjustments (date pickers, time slot selector) prior to confirmation.
    * Features primary action: `[ Confirm & Add to Calendar ]`.
    * Form submission executes via `POST /appointments/confirm`.
  * **If Status == `CONFIRMED`:**
    * Displays the active booking details.
    * Exposes explicit controls: `[ Reschedule Appointment ]` and `[ Cancel Appointment ]`.
  * **If Status == `CANCELLED`:**
    * Displays cancellation notice and an option to re-book.

### Step 3: Outbound Calendar Dispatch (`SEQUENCE: 0`)
* **Trigger:** Form submission on landing page (`POST /appointments/confirm`).
* **Database Actions:**
  * Update appointment status to `CONFIRMED`.
  * Initialize `ics_sequence = 0`.
* **Outbound Action:** System dispatches an email containing the RFC-5545 `.ics` payload.
* **Calendar Payload Rules:**
  * `METHOD: REQUEST`
  * Persistent `UID` (e.g., `booking-<id>@dad4dogs.ca`).
  * `SEQUENCE: 0`
  * `STATUS: CONFIRMED`
  * `DESCRIPTION` explicitly includes the secure management URL back to the landing page.

### Step 4: Rescheduling & Modifications (`SEQUENCE: N + 1`)
* **Trigger:** Customer reschedules via the management portal.
* **Database Actions:**
  * Update start and end timestamps.
  * Increment `ics_sequence = ics_sequence + 1`.
* **Outbound Action:** Send updated `.ics` payload.
* **Calendar Payload Rules:**
  * `METHOD: REQUEST`
  * Same `UID`.
  * Incremented `SEQUENCE`.
  * Updated `DTSTART` and `DTEND`.
  * Modern calendar clients (Outlook, iOS Calendar, Google) detect the matching `UID` and higher `SEQUENCE` number and automatically shift the event to the new time slot without duplication.

### Step 5: Cancellations (`METHOD: CANCEL`)
* **Trigger:** Customer clicks `[ Cancel Appointment ]` on the management page.
* **Database Actions:**
  * Update appointment status to `CANCELLED`.
  * Increment `ics_sequence = ics_sequence + 1`.
* **Outbound Action:** Send cancellation `.ics` payload.
* **Calendar Payload Rules:**
  * `METHOD: CANCEL`
  * Same `UID`.
  * Incremented `SEQUENCE`.
  * `STATUS: CANCELLED`
  * Instructs native calendar clients to automatically drop the event from the schedule.

---

## 4. RFC-5545 Payload Reference Examples

### A. Initial Confirmation Payload (`SEQUENCE: 0`)
```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dad 4 Dogs//Dog Sitting Engine//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:booking-2026-9812@dad4dogs.ca
SEQUENCE:0
STATUS:CONFIRMED
DTSTAMP:20260902T150000Z
DTSTART:20260910T130000Z
DTEND:20260910T170000Z
SUMMARY:Dog Sitting - Buster
LOCATION:191 Grey Street, London, ON
DESCRIPTION:Buster's dog sitting session with Dad 4 Dogs.\n\nTo reschedule or cancel, visit: https://app.dad4dogs.ca/appointments/manage?token=a8f9b2c4e1d743
ORGANIZER;CN=Dad 4 Dogs:mailto:noreply@dad4dogs.ca
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;CN=Client:mailto:client@example.com
END:VEVENT
END:VCALENDAR
```

### B. Reschedule Payload (`SEQUENCE: 1`)
```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dad 4 Dogs//Dog Sitting Engine//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:booking-2026-9812@dad4dogs.ca
SEQUENCE:1
STATUS:CONFIRMED
DTSTAMP:20260903T100000Z
DTSTART:20260911T140000Z
DTEND:20260911T180000Z
SUMMARY:Dog Sitting - Buster
LOCATION:191 Grey Street, London, ON
DESCRIPTION:Buster's dog sitting session with Dad 4 Dogs (UPDATED).\n\nTo reschedule or cancel, visit: https://app.dad4dogs.ca/appointments/manage?token=a8f9b2c4e1d743
ORGANIZER;CN=Dad 4 Dogs:mailto:noreply@dad4dogs.ca
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;CN=Client:mailto:client@example.com
END:VEVENT
END:VCALENDAR
```

### C. Cancellation Payload (`METHOD: CANCEL`)
```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Dad 4 Dogs//Dog Sitting Engine//EN
CALSCALE:GREGORIAN
METHOD:CANCEL
BEGIN:VEVENT
UID:booking-2026-9812@dad4dogs.ca
SEQUENCE:2
STATUS:CANCELLED
DTSTAMP:20260904T120000Z
DTSTART:20260911T140000Z
DTEND:20260911T180000Z
SUMMARY:Dog Sitting - Buster (CANCELLED)
ORGANIZER;CN=Dad 4 Dogs:mailto:noreply@dad4dogs.ca
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;CN=Client:mailto:client@example.com
END:VEVENT
END:VCALENDAR
```

---

## 5. Architectural Benefits

1. **Deterministic State Machine:** The database is the sole authority. No ambiguous intermediate states caused by unread emails or dropped webhooks.
2. **Zero Inbound Parsing:** Eliminates complex MIME parsing, MX record forwarding, spam-filter drops, and varied vendor reply formats.
3. **Friction-Free Client Experience:** No customer logins, passwords, or OAuth calendar permission grants required.
4. **Brand Engagement:** Re-engages pet owners directly on your custom web portal whenever an appointment is managed or altered.
