# Scheduling: Calendar & booking email

**Load for:** confirmation email MIME/ICS, VEVENT fields, `/ical/`, inbound pending events, Gmail OAuth failures.  
**Related:** [`booking.md`](booking.md) (opt-in checkbox / send UX)  
**Services:** `visit_email.py`, `gmail_send.py`, `ical_feed.py`, `gmail_sync.py`

---

## Booking confirmation send

- Opt-in on create (default off); one email covers a repeat series; stamps `confirmation_email_sent_at`
- Resend: `POST /visits/<id>/send-confirmation/` — already-sent = no-op; Gmail errors flash warning; visit unchanged
- `RefreshError` / invalid_grant → `GmailSendError` → `VisitEmailError`; **never 500** the booking. Fix tokens: `python oauth_setup.py`
- `business_email` required before sending; should match Gmail send-as

---

## Calendar invite layers

1. **Inline MIME** — `text/calendar; method=REQUEST` inside `multipart/alternative` (Gmail banner)
2. **Attachment** — `dad4dogs_booking.ics`
3. **Repeat series** — one `.ics`, multiple `VEVENT` (`generate_booking_ics()`)

### VEVENT fields

Organizer/location from **Business Settings** (`BusinessProfile`):

| Field | Source |
| --- | --- |
| `LOCATION` | `BusinessProfile.address` (omit if blank) |
| `ORGANIZER` | `business_email` + `business_name` (CN=) |
| `ATTENDEE` (client) | `visit.client.owner_email`; `RSVP=TRUE`, `PARTSTAT=NEEDS-ACTION` |
| `ATTENDEE` (organizer) | Same `business_email`; `RSVP=FALSE` |
| `DESCRIPTION` | Dog, owner, optional `BOOKING_CLIENT_NOTES_URL`, notes |
| `UID` | `visit_{id}@{ICAL_UID_DOMAIN}` |
| `STATUS` / `SEQUENCE` | `CONFIRMED` / `0` |

Env (`config/settings.py`):

- `BOOKING_CLIENT_NOTES_URL` — iCal `DESCRIPTION`
- `PUBLIC_SITE_URL` — plain-text email may include feed link `/feed/<secret>/<dog>/`

METHOD:UPDATE/CANCEL — not yet built.

---

## Outbound iCal feed

`/ical/` — `ical_feed.py` read-only feed for Google Calendar subscription (linked from dashboard Calendar feed disclosure).

---

## Inbound (partial)

- `python manage.py import_calendar path/to/file.ics` → `PendingCalendarEvent`
- David reviews at `/calendar/pending/`
- `approve_pending_event` → `Visit.objects.create()` (full `save()` / capacity). Catch `ValidationError`, flash, leave **pending** on failure — do not 500
- `gmail_sync.py` — client matching helpers; no live Gmail read yet

**Tests:** `VisitEmailTests`, `PendingEventApproveTests`.
