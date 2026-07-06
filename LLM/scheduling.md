# Domain: Scheduling

**Covers:** visits, repeat series, dashboard agenda, check-in/out, pricing, capacity, calendar sync, booking confirmation email.

**Code packages:** `operations/models/scheduling.py`, `forms/scheduling.py`, `views/scheduling.py`  
**Root modules:** `operations/pricing.py`, `operations/capacity.py`  
**Services:** `agenda.py`, `datetime_parse.py`, `visit_repeat.py`, `visit_email.py`, `gmail_send.py`, `ical_feed.py`, `gmail_sync.py`

---

## 1. Data Model

| Model | Purpose |
|-------|---------|
| `VisitSeries` | Groups recurring visits created in one booking |
| `Visit` | Single scheduled/checked-in/completed stay |
| `PendingCalendarEvent` | Inbound calendar events awaiting David's review |

### Visit statuses
`scheduled` → `checked_in` → `completed` (or `cancelled`)

### Visit key fields
- `scheduled_start`, `scheduled_end` — authoritative booking window
- `actual_arrival`, `actual_departure` — set at check-in/out
- `calculated_fee`, `fee_breakdown` — set at checkout (JSON-safe strings in breakdown)
- `confirmation_email_sent_at` — when booking confirmation was emailed
- `series`, `series_position` — link to repeat series

### Visit methods
- `check_in()`, `check_out()` — checkout runs pricing engine
- `clone_to_date(new_date)` — same duration/time-of-day on new date
- `schedule_display` — human-readable range property
- `is_editable` — scheduled visits only

---

## 2. Visit Booking UX

David books per **dog**. Two free-text fields only — **no multi-step date/time pickers**.

| Field | Example |
|-------|---------|
| Start | `April 11, 2026 5 pm` |
| End | `April 28, 2026 5 pm` |

### Parse flow
1. Type or dictate (phone keyboard speech-to-text)
2. Blur → `/visits/parse-datetime/` returns formatted preview
3. Tap preview to edit raw text
4. Server parse on submit is authoritative (`datetime_parse.py`)

### Repeat (create only — not on edit)
- **Repeat:** none | daily | weekly | weekdays | monthly
- **Every** N days/weeks/months
- **Ends:** number (`5`) or date (`April 15, 2026`) — auto-detected
- Max 52 occurrences; capacity checked for **every** occurrence (whole series fails if any day blocked)
- `VisitForm.save_all()` creates series + visits in one transaction

### Clone past visit
On visit create page: select completed visit + new start date → copies duration/time-of-day.

### Booking confirmation email
- Checkbox on create: **Send booking confirmation to {email}**
- Unchecked by default — David must opt in
- Sends via Gmail OAuth (`visit_email.py` → `gmail_send.py`)
- One email covers all visits in a repeat series
- Success message + `Email sent` badge on dog detail
- `confirmation_email_sent_at` stamped on each visit

### Calendar invite layers (booking email)
1. **Inline MIME** — `text/calendar; method=REQUEST` inside `multipart/alternative` (Gmail interactive banner)
2. **Attachment** — `dad4dogs_booking.ics` fail-safe for double-click import
3. **Repeat series** — one `.ics` with multiple `VEVENT` blocks (`generate_booking_ics()`)

### VEVENT fields (`generate_booking_ics()`)
All organizer and location data comes from **Business Settings** (`/settings/`, `BusinessProfile`).

| Field | Source |
|-------|--------|
| `LOCATION` | `BusinessProfile.address` — omitted if blank |
| `ORGANIZER` | `BusinessProfile.business_email` + `business_name` (CN=) |
| `ATTENDEE` (client) | `visit.client.owner_email`; `RSVP=TRUE`, `PARTSTAT=NEEDS-ACTION` |
| `ATTENDEE` (organizer) | Same `business_email`; `RSVP=FALSE` (David already knows) |
| `DESCRIPTION` | Dog, owner, optional `BOOKING_CLIENT_NOTES_URL`, visit notes |
| `UID` | `visit_{id}@{ICAL_UID_DOMAIN}` — stable for future update/cancel support |
| `STATUS` / `SEQUENCE` | `CONFIRMED` / `0` — foundation for METHOD:UPDATE/CANCEL |

`business_email` is **required** before sending a booking invite. It should match the authenticated Gmail send-as address.  
Optional env: `BOOKING_CLIENT_NOTES_URL` in `config/settings.py`.

Updates/cancellations (METHOD:UPDATE/CANCEL) — not yet built

---

## 3. URLs

| Path | Purpose |
|------|---------|
| `/` | Dashboard — month calendar + daily agenda |
| `/checkin/` | Mobile check-in/out |
| `/dogs/<id>/visits/add/` | Schedule visit (+ repeat + clone) |
| `/visits/<id>/edit/` | Edit scheduled visit only |
| `/visits/<id>/delete/` | POST — scheduled only |
| `/visits/parse-datetime/` | JSON parse preview |
| `/visits/<id>/check-in/` | POST |
| `/visits/<id>/check-out/` | POST — calculates fee |
| `/calendar/pending/` | Review imported calendar events |
| `/ical/` | Public read-only iCal feed |

---

## 4. Dashboard & Agenda

Home screen (`/`) = David's daily operations view.

### Month calendar
- Monday-first grid; prev/next month
- Dot on days with visits; today outlined; selected day filled green
- Click day → `?year=&month=&date=YYYY-MM-DD`

### Daily agenda
- All visits **overlapping** selected day (overnight spans included)
- Checked-in: amber background + badge
- Scheduled: green left border
- Completed: muted grey
- Capacity stats for **selected** day

### Overlap query (same as capacity)
`scheduled_start < day_end` AND `scheduled_end > day_start`

---

## 5. Check-In / Check-Out

- `/checkin/` lists today's overlapping scheduled + checked-in visits
- Check-in sets `actual_arrival = now`, status `checked_in`
- Check-out sets `actual_departure = now`, runs `calculate_fee()`, status `completed`
- Capacity re-checked at check-in

---

## 6. Pricing Engine (`pricing.py`)

See `PROJECT.md` §5 for tier table.

- `calculate_fee(arrival, departure)` → `(Decimal total, list[line_items])`
- Line items use **string amounts** for JSONField compatibility
- `is_overnight_segment()` checked before hour tiers
- Multi-day: full 24h blocks = Overnight; remainder priced separately

Tests: `PricingEngineTests`, `VisitCheckOutTests`

---

## 7. Capacity (`capacity.py`)

| Count | Behaviour |
|-------|-----------|
| ≥ 9 dogs | Warning |
| > 10 dogs | Block (insurance ceiling) |

Counts distinct `client_id` with visits overlapping the calendar day. Validated on `Visit.save()` and at check-in.

---

## 8. Calendar Sync

### Outbound (done)
- `/ical/` — `ical_feed.py` generates read-only feed for Google Calendar subscription

### Inbound (partial)
- `python manage.py import_calendar path/to/file.ics`
- Creates `PendingCalendarEvent`; David approves at `/calendar/pending/`
- `gmail_sync.py` — client matching helpers; no live Gmail read yet

---

## 9. Forms & Views Files

| File | Contents |
|------|----------|
| `forms/scheduling.py` | `VisitForm`, `VisitScheduleForm` alias |
| `views/scheduling.py` | `dashboard`, `mobile_checkin`, `visit_*`, `pending_events`, `parse_datetime_field`, `ical_feed` |

---

## 10. Tests

`VisitFormTests`, `DatetimeParseTests`, `AgendaTests`, `PricingEngineTests`, `VisitCheckOutTests`, `VisitEmailTests` in `operations/tests.py`.

---

## 11. Not Yet Built

- Per-dog contemporaneous day notes during active visits
- Live Gmail calendar read (inbound)
- Edit/delete entire repeat series at once