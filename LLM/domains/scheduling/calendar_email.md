# Scheduling: Calendar & booking email

**Load for:** client review/confirm links, ICS REQUEST/CANCEL + SEQUENCE, `/ical/`, parked inbound pending events, Gmail OAuth failures.  
**Related:** [`booking.md`](booking.md) (staff create/edit UX)  
**Architecture decision:** `LLM/decisions/calendar_sync_architecture_plan.md`  
**Services (target):** `visit_email.py` / optional `visit_ics.py`, `gmail_send.py`, `ical_feed.py`; manage views under `views/scheduling/`

**Status:** Spec **accepted**; **C1–C3 landed** (invite fields, manage page, Email A review link on staff send, Email B ICS after client confirm / confirm-series / approve-change). **C4–C5 next** (staff edit → Email C by default, immediate-ICS override checkbox, badges, MIME CANCEL method header polish).

---

## Design (unidirectional)

The app DB is the **source of truth**. The client’s Apple/Google/Outlook calendar is a **downstream consumer** of `.ics` only.

- **No** live Gmail calendar API read for client sync.
- **No** parsing of inbound ACCEPT/DECLINE MIME.
- **No** ICS until a human **POST** on the branded manage page — except the explicit staff override below.
- GET on the manage URL must be idempotent (SafeLinks / virus scanners must not confirm).

### Operator → client flow

1. Staff creates `Visit` (`status=scheduled`, capacity as today).
2. **Email A** (optional): “Review & confirm” — plain transactional email, **no** `.ics` → manage URL with per-visit token.
3. Client GET manage page → POST **Confirm** (or **Confirm all in series**).
4. **Email B**: `METHOD:REQUEST`, `SEQUENCE:0`, manage URL in `DESCRIPTION`.
5. Later staff time/cancel change (default): **Email C** review link only → client approves → **Email B′** with `SEQUENCE+=1` (`REQUEST` or `CANCEL`).
6. Staff override on edit: checkbox **Send updated calendar invite immediately** → skip Email C; bump sequence and send ICS on save.

### Calendar invite lifecycle (orthogonal to `Visit.status`)

Do **not** overload `scheduled` / `checked_in` / `completed` / `cancelled`.

| Field | Role |
| --- | --- |
| `calendar_manage_token` | Capability token (feed-style); regenerate invalidates old links |
| `ics_uid` | Stable UID (`visit_{id}@{ICAL_UID_DOMAIN}` or stored) |
| `ics_sequence` | Last SEQUENCE value included in an outbound ICS |
| `calendar_invite_state` | `none` → `awaiting_confirm` → `invite_issued` → `awaiting_change_confirm` → `cancelled_invite` |
| `calendar_review_sent_at` | Last Email A / C (no ICS) |
| `calendar_invite_sent_at` | Last Email B / B′ (ICS) |

Legacy `confirmation_email_sent_at` is replaced by the clearer stamps above as C1 migrates call sites.

**Tokens:** one per visit. **Series:** manage page for any sibling may offer **Confirm all visits in this series** (one POST flips every `awaiting_confirm` sibling). Outbound ICS still uses **one VEVENT per visit**, each `DESCRIPTION` carrying **that visit’s** manage link.

---

## Manage page (public)

Route: `/bookings/manage/<token>/` (`operations:booking_manage`).

| State | Client actions |
| --- | --- |
| `awaiting_confirm` | Confirm & add to calendar; optional **Confirm all in series**; may adjust date/time before confirm (capacity + same-dog overlap) |
| `invite_issued` | Reschedule (inline date/time + capacity) or Cancel |
| `awaiting_change_confirm` | Approve staff update, Reschedule, or Cancel |
| `cancelled_invite` | Cancelled notice |

All commits are POST-only.

---

## Outbound ICS rules

| Event | METHOD | SEQUENCE | STATUS |
| --- | --- | --- | --- |
| First client confirm | `REQUEST` | `0` | `CONFIRMED` |
| Approved / immediate reschedule | `REQUEST` | prior + 1 | `CONFIRMED` |
| Approved / immediate cancel | `CANCEL` | prior + 1 | `CANCELLED` |

- Same `UID` for the life of the visit.
- `ATTENDEE` client `PARTSTAT=ACCEPTED` after web confirm (consent already collected).
- `ORGANIZER` / `LOCATION` from `BusinessProfile`; refuse send if business email missing.
- Layers when ICS is sent: inline `text/calendar` MIME + `dad4dogs_booking.ics` attachment (same as today).
- Repeat series Email B: one `.ics`, multiple `VEVENT`s.

Env (`config/settings.py`): `BOOKING_CLIENT_NOTES_URL`, `PUBLIC_SITE_URL`, `ICAL_UID_DOMAIN`.

---

## Staff UX

| Action | Behaviour |
| --- | --- |
| Create checkbox | **Send review & confirm link** (default **off**) → Email A only |
| Edit/cancel after `invite_issued` (default) | Queue Email C; set `awaiting_change_confirm`; **no** ICS yet |
| Edit checkbox **Send updated calendar invite immediately** | Skip Email C; `ics_sequence += 1`; send REQUEST or CANCEL now |
| Visits list | Show invite state (awaiting confirm / invite sent / awaiting change confirm) |

OAuth failures → `GmailSendError` / `VisitEmailError`; **never 500** the booking. Fix tokens: `python oauth_setup.py`.

---

## Outbound iCal feed (staff)

`/ical/` — `ical_feed.py` read-only subscription for **David’s** Google Calendar. Unrelated to client invite lifecycle; keep as-is.

---

## Inbound (parked / deprecated for client sync)

File import → `PendingCalendarEvent` → `/calendar/pending/` remains in code for possible staff bulk import, but is **not** the client calendar architecture and is **not** next backlog. No live Gmail calendar read.

**Tests (as slices land):** manage GET/POST, series confirm-all, SEQUENCE/CANCEL, staff override immediate send — under `operations/tests/scheduling/` (`test_calendar.py` and related).
