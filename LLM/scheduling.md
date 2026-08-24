# Domain: Scheduling

**Covers:** visits, repeat series, dashboard agenda, check-in/out, pricing, capacity, calendar sync, booking confirmation email.

**Code packages:** `operations/models/scheduling.py`, `forms/scheduling.py`, `views/scheduling.py`  
**Root modules:** `operations/pricing.py`, `operations/capacity.py`  
**Services:** `agenda.py`, `datetime_parse.py`, `visit_repeat.py`, `visit_email.py`, `gmail_send.py`, `ical_feed.py`, `gmail_sync.py`, `timeline_media.py`, `timeline_visits.py`, `geolocation.py`  
**Customer feed:** see [`feed.md`](feed.md) — public read-only view of timeline media

---

## 1. Data Model

| Model | Purpose |
|-------|---------|
| `VisitSeries` | Groups recurring visits created in one booking |
| `Visit` | Single scheduled/checked-in/completed stay |
| `PendingCalendarEvent` | Inbound calendar events awaiting David's review |
| `TimelineMediaAsset` | Immutable photo/video capture (GPS, caption, timestamps) |
| `VisitTimelineEvent` | Links media asset to a visit; supports forward to other checked-in dogs |

### Visit statuses
`scheduled` → `checked_in` → `completed` (or `cancelled`)

Forward only via `Visit.check_in()` / `Visit.check_out()`. Do not assign `status`, `actual_arrival`, `actual_departure`, or `calculated_fee` in views to “fix” a transition.

### Visit key fields
- `scheduled_start`, `scheduled_end` — authoritative booking window
- `actual_arrival`, `actual_departure` — set at check-in/out
- `calculated_fee`, `fee_breakdown` — set at checkout (JSON-safe strings in breakdown)
- `confirmation_email_sent_at` — when booking confirmation was emailed
- `series`, `series_position` — link to repeat series

### Visit indexes (`Visit.Meta.indexes`)
Single-column indexes on the hot lookup fields used by capacity, agenda, check-in, and iCal:

| Index name | Field | Why |
|------------|-------|-----|
| `visit_scheduled_start_idx` | `scheduled_start` | Day overlap (`scheduled_start__lt=day_end`), agenda order |
| `visit_scheduled_end_idx` | `scheduled_end` | Day overlap (`scheduled_end__gt=day_start`) |
| `visit_status_idx` | `status` | `status__in` on capacity, agenda, check-in, timeline eligibility |

Do not drop these to “simplify” Meta. `client` already has an FK index. A composite `(status, scheduled_start, scheduled_end)` is **not** a substitute — overlap queries (`start < day_end AND end > day_start`) need both ends independently.

Migration: `0016_visit_hot_lookup_indexes`.

### Visit methods
- `check_in()` — only from `scheduled`; sets `actual_arrival`
- `check_out()` — only from `checked_in` with no `calculated_fee`; sets `actual_departure` and runs pricing once
- Illegal transitions raise `ValidationError` (mobile double-tap / stale POST must not overwrite times or fees)
- `save()` — `full_clean()` (end-after-start + capacity) on booking writes; skipped for status-only `update_fields` (see §5 and §7)
- `clone_to_date(new_date)` — same duration + **local** time-of-day on `new_date` (`datetime.combine`, not `datetime.replace`)
- `schedule_display` — human-readable range property
- `is_editable` — scheduled visits only
- `accepts_timeline_events` — `True` only while `checked_in`

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

### Standard-stay readiness (create only)
`VisitForm.clean()` calls `ClientProfile.standard_stay_blockers()` on **create** (not edit). Hard form errors (non-field) if any of:

- Pipeline is not **Approved** (Inquiry / Meet & Greet / Evaluation cannot book a standard stay)
- No current validated vaccination (`has_current_vaccination`)
- Owner COI not confirmed (`CustomerOwner.coi_confirmed_received`)
- Dog is **hidden** (`is_hidden`) — cannot book a new stay; existing visits still check in/out

Clone (`clone_to_date`), calendar approve, and **intake Meet & Greet** (`IntakeWizardForm`) still bypass the form gate. Do not put this gate on `Visit.save()` — that would block check-in `update_fields` if we ever full_clean those rows.

### Repeat (create only — not on edit)
- **Repeat:** none | daily | weekly | weekdays | monthly
- **Every** N days/weeks/months
- **Ends:** number (`5`) or date (`April 15, 2026`) — auto-detected
- Max 52 occurrences (`MAX_OCCURRENCES`). Count “Ends” of 53+ is rejected in `parse_repeat_ends`. An **until date** that would produce more than 52 visits is a `repeat_ends` error in `VisitForm.clean()` — do not silently clip to 52. `len(occurrences) > 52` is also rejected there so a generator change cannot create a huge series.
- Capacity runs in `VisitForm.clean()` — blocked days are **non-field form errors** (`visit_form.html` already shows them). `save_all()` only writes after `is_valid()` and calls `visit.save(skip_capacity=True)` so series creation does not query capacity a second time per occurrence. Direct `Visit.save()`, clone, and admin still run the check.
- `VisitForm.save_all()` creates series + visits in one transaction
- **Edit** (`self.instance`): `save(update_fields=['scheduled_start', 'scheduled_end', 'notes', 'updated_at'], skip_capacity=True)` — do not write status, fees, series, or `confirmation_email_sent_at` from a stale in-memory instance. New visits still save the full row.
- `VisitSeries` is created when **Repeat** is not “Does not repeat” — including a series of **one** visit (`Ends: 1`, or an until-date that yields a single occurrence). Skipping the series when `len(occurrences) == 1` used to drop frequency/interval. A non-repeating booking still has `series=None`.

### Clone past visit
On visit create page: select completed visit + new start date → copies duration and **local** time-of-day.

`clone_to_date(new_date)` localizes `scheduled_start`, then `datetime.combine(new_date, start.time(), tzinfo=start.tzinfo)`, then adds the original duration. Do **not** use `datetime.replace(year=, month=, day=)`:

- A visit on the 31st cloned onto Feb 28 / April 30 raises `ValueError` (day out of range) if you replace the month while the day is still 31.
- `replace` on a UTC instant can shift the clock across DST; combine keeps 5 PM local as 5 PM local.

Overnight stays keep the same length (end is start + duration, not a replaced end clock). Capacity still runs because create goes through `Visit.save()`.

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

Optional env vars (`config/settings.py`):
- `BOOKING_CLIENT_NOTES_URL` — embedded in iCal `DESCRIPTION`
- `PUBLIC_SITE_URL` — when set, plain-text confirmation email includes customer **photo feed** link (`/feed/<secret>/<dog>/`)

Updates/cancellations (METHOD:UPDATE/CANCEL) — not yet built

---

## 3. URLs

Every view in `views/scheduling.py` declares allowed methods (`@require_GET`, `@require_POST`, or `@require_http_methods(['GET', 'POST'])`). Wrong verbs return **405**.

| Path | Methods | Purpose |
|------|---------|---------|
| `/` | GET | Dashboard — month calendar + daily agenda |
| `/checkin/` | GET | Mobile check-in/out |
| `/dogs/<id>/visits/add/` | GET, POST | Schedule visit (+ repeat + clone) |
| `/visits/<id>/edit/` | GET, POST | Edit scheduled visit only |
| `/visits/<id>/delete/` | POST | scheduled only |
| `/visits/parse-datetime/` | GET | JSON parse preview |
| `/visits/<id>/check-in/` | POST — `check_in()`; illegal status → error message, no write |
| `/visits/<id>/check-out/` | POST — `check_out()` + fee; illegal status → error message, no write |
| `/visits/<id>/timeline/` | Log moment (photo/video) while checked in |
| `/visits/<id>/timeline/<event>/forward/` | POST — share moment to other checked-in dogs |
| `/calendar/pending/` | Review imported calendar events |
| `/ical/` | Public read-only iCal feed (David's calendar) |
| `/feed/<secret>/<dog>/` | Public customer photo feed — see `feed.md` |

---

## 4. Dashboard & Agenda

Home screen (`/`) = David's daily operations view.

### Month calendar
- Monday-first grid; prev/next month
- Dot on days with visits; today outlined; selected day filled green
- Click day → `?year=&month=&date=YYYY-MM-DD`
- Query `year` must be `datetime.MINYEAR`…`MAXYEAR` (1–9999); `month` 1–12. Out-of-range or huge integers fall back to the selected day’s month — do not call `date(cal_year, …)` unbounded (`OverflowError` / `ValueError`).

### Daily agenda
- Compact rows: `Dog · Owner` plus time; tap opens dog detail
- Checked-in: amber left border + **CHECKED IN** badge only
- Scheduled: green left border, no status badge
- Completed: muted grey, no green COMPLETED badge
- Occupancy is `capacity.count` (distinct dogs that day). Denominator is Settings **standard** capacity (default 8); insurance max is the booking hard stop (default 10). Empty days show **0 / standard**, not a bare 0. Always show the `N of standard` line; **WARNING/OVER** badge only when not ok. Do not hide the denominator when status is ok.
- **Open Check-In** on today
- iCal link is in a **Calendar feed** disclosure (not a permanent Quick Links card)

### Vaccination compliance cards
- Shown **only when the count is > 0** (no always-on Approved Dogs / Standard Max tiles)
- **Vax Expiring (30d)** — latest validated `expires_at` is today through today+30; links to `/clients/?vax=expiring`
- **Vax Expired** — latest validated `expires_at` already past; links to `/clients/?vax=expired`
- Counts come from `ClientProfile.objects.vaccination_status_counts()` (one annotated aggregate). Do not N+1 `has_current_vaccination` on the dashboard.

### Overlap query (same as capacity, check-in, feed activity, timeline eligibility)
`scheduled_start < day_end` AND `scheduled_end > day_start` where bounds are **local** midnight from `agenda.day_bounds()`. Do **not** use `scheduled_start__date` / `scheduled_end__date` — SQLite `__date__` on aware datetimes is UTC-ish and drops overnight stays that cross midnight.

---

## 5. Check-In / Check-Out

- `/checkin/` lists today's overlapping scheduled + checked-in visits (`day_bounds`, not `__date__`)
- Each card: dog, owner, tap-to-call (emergency vet if present, else clinic). No green OK badges.
- Scheduled: one CTA (**Check In**). Checked-in: **Log Moment** + **Check Out**.
- Capacity count always; WARNING/OVER badge only when not ok
- Check-in sets `actual_arrival = now`, status `checked_in`
- Check-out sets `actual_departure = now`, runs `calculate_fee()`, status `completed`
- Capacity re-checked at check-in
- Checked-in cards show **Log Moment** → staff timeline (`visit_timeline`)
- **Owner feed activity** panel — polls `/checkin/feed-activity/` every 15s for owner/family reactions and comments on the customer feed (standard emoji labels in JSON)

### Status guards (idempotent transitions)

David’s phone can double-tap Check In / Check Out or replay a stale POST. A second call must **not** overwrite `actual_arrival`, re-run pricing with a later `actual_departure`, or complete a visit that was never checked in.

| Method | Allowed from | On success | Otherwise |
|--------|--------------|------------|-----------|
| `check_in()` | `scheduled` only | `actual_arrival = now`, status `checked_in` | `ValidationError` — no field writes |
| `check_out()` | `checked_in` **and** `calculated_fee` is null | `actual_departure = now`, `calculate_fee()`, status `completed` | `ValidationError` — no field writes |

Cancelled and completed visits cannot enter either method.

**Views** (`visit_check_in`, `visit_check_out`): catch `ValidationError`, flash the message, redirect back to `/checkin/`. Do not 500 on a double-tap.

Do **not** turn the already-correct status into a silent no-op unless David asks — a refused transition is an error, not a second success. The template already hides the wrong button; the guard is for stale POSTs and any future caller.

`check_out()` re-reads the row (`refresh_from_db`) before pricing. A stale in-memory instance that still says `checked_in` must not re-run `calculate_fee()` or overwrite `calculated_fee` / `fee_breakdown`. If `calculated_fee` is already set, raise and skip pricing — even when status was left `checked_in`.

`check_in()` / `check_out()` save with `update_fields` so capacity is **not** re-run. A day that is already at or over the insurance ceiling must not trap a dog that is already on site.

**Tests:** `VisitCheckOutTests` (model refusals leave arrival/fee/status unchanged; stale instance does not re-run `calculate_fee`), `VisitCheckInOutViewTests` (double POST keeps the first arrival / fee), and `VisitCapacitySaveTests` (checkout/check-in still work when the day is over ceiling). Keep those green if you touch check-in, check-out, or `Visit.save()`.

---

## 5b. Contemporaneous Timeline (staff)

David logs photos/videos during active check-in. Customers see the same media later on their **feed link** (read-only).

### Rules
- Capture only while visit is `checked_in`
- Forward only to **other currently checked-in** visits (same day overlap)
- One `TimelineMediaAsset` per capture; forwards create new `VisitTimelineEvent` rows sharing the asset
- GPS from device; fallback coords from `BUSINESS_FALLBACK_LATITUDE/LONGITUDE`
- Video max size: `TIMELINE_VIDEO_MAX_BYTES` (25 MB)

### Forms
`TimelineMomentForm`, `TimelineForwardForm` in `forms/scheduling.py`. Moment form: exactly one of camera photo, gallery photo, or video — camera+gallery is a validation error, not camera-wins. Lat/long: blank (GPS fallback) or both valid decimals in range.

### Full detail
See [`feed.md`](feed.md) for model fields, customer feed URLs, and security model.

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

**Purpose:** Standard is the comfortable daily count (dashboard `N / standard`, warning when over). Insurance max is the policy hard stop (block **new** bookings when a day would go over). Both live on `BusinessProfile` and are edited on `/settings/` — see `admin.md` §2 Daily capacity.

**How:** `capacity.capacity_limits()` reads `standard_capacity` / `insurance_ceiling` from the singleton (`values_list`, no `load()`). Missing row → module defaults 8 / 10. Do not hardcode 8/10 in templates or booking checks; use `capacity.standard` / `capacity.ceiling` from `assess_capacity`.

| Count | Behaviour |
|-------|-----------|
| ≤ standard | OK — dashboard shows `N / standard` |
| standard < count ≤ insurance | Warning |
| > insurance | Block (new bookings) |

Counts distinct `client_id` with visits overlapping the calendar day (`scheduled`, `checked_in`, and `completed`). Filter uses `status`, `scheduled_start`, `scheduled_end` — keep the `Visit.Meta` indexes on those fields.

`count_dogs_on_day` uses `Count('client_id', distinct=True)` in SQL — do not `values_list` into a Python set. If `include_client_id` is set, the same aggregate checks whether that dog is already in the day (`Count` + `filter=Q(client_id=…)`) and adds 1 only when missing.

Day windows use Django’s `timezone.get_current_timezone()` (`America/Toronto`) via `_day_bounds` — **not** `datetime.now().astimezone()` (that is the host OS zone; a UTC server would shift overnight counts). `check_visit_capacity` walks `_capacity_span_dates()` via `_as_local()`: `timezone.localtime()` after `make_aware` if naive. Do **not** use `visit.scheduled_start.tzinfo` / `.astimezone(tz)` — naive datetimes have `tzinfo is None` and crash. If `scheduled_end` is **exactly local midnight**, that instant belongs to the **prior** day only — SQL is `scheduled_end > day_start`, so `2026-04-12 00:00` does not occupy 12 April.

`check_visit_capacity` loads overlapping visits for **`[start_day, end_day]` in one query** (`_daily_dog_counts`), then counts distinct `client_id` per day in memory. Plus one query for Settings limits. Do **not** call `assess_capacity()` once per day (N+1 on a 14-day stay). Dashboard/check-in still use `assess_capacity` for a **single** day.

Booking forms call `check_visit_capacity` in `VisitForm.clean()` (not in `save_all()`), so a full day is a form error and no `VisitSeries` / visits are created.

Capacity is a **booking** rule, not a day-of-ops lock:

| Write | Runs `full_clean()` / `check_visit_capacity()`? |
|-------|--------------------------------------------------|
| `Visit.save()` with no `update_fields` (create, edit times, clone, admin) | Yes — block if any spanned day is over the insurance ceiling |
| `VisitForm.save_all()` after a valid `clean()` | `full_clean()` **yes** (end-after-start); capacity query **no** (`skip_capacity=True`). Edits use `update_fields` for start/end/notes/`updated_at` only. |
| `save(update_fields=…)` that includes `scheduled_start`, `scheduled_end`, or `client` | Yes |
| `check_in()` / `check_out()` (status, timestamps, fee) | **No** — the visit is already on the books |
| Check-in **view** (`visit_check_in`) | Still `assess_capacity` for a warning/block *message*; model save does not re-block |

Do not call `full_clean()` from `check_in()` / `check_out()`. Do not pass `skip_capacity=True` from views, clone, or admin — only `VisitForm.save_all()`. If you change scheduled times outside the form, `save()` without `skip_capacity` so capacity still runs.

**Tests:** `VisitCapacitySaveTests` (includes `test_settings_ceiling_blocks_below_default`), `CapacityTimezoneTests`, `BusinessProfileTests` / `BusinessSettingsViewTests` (form + dashboard `0 / 6` after save) in `operations/tests.py`.

---

## 8. Calendar Sync

### Outbound (done)
- `/ical/` — `ical_feed.py` generates read-only feed for Google Calendar subscription

### Inbound (partial)
- `python manage.py import_calendar path/to/file.ics`
- Creates `PendingCalendarEvent`; David approves at `/calendar/pending/`
- `approve_pending_event` uses `Visit.objects.create()` (full `save()` / capacity). Catch `ValidationError` and flash it — do not 500; leave the event **pending** if create fails (full day, end-before-start, etc.).
- `gmail_sync.py` — client matching helpers; no live Gmail read yet

---

## 9. Forms & Views Files

| File | Contents |
|------|----------|
| `forms/scheduling.py` | `VisitForm` (parse + repeat + capacity in `clean()`), `VisitScheduleForm` alias |
| `views/scheduling.py` | `dashboard`, `mobile_checkin`, `visit_*`, `visit_timeline*` (shared forward-target queryset on GET), `pending_events`, `parse_datetime_field`, `ical_feed` |

---

## 10. Tests

`VisitFormTests`, `DatetimeParseTests`, `AgendaTests`, `DashboardViewTests`, `PricingEngineTests`, `VisitCheckOutTests`, `VisitCheckInOutViewTests`, `VisitCapacitySaveTests`, `PendingEventApproveTests`, `VisitIndexTests`, `VisitCloneToDateTests`, `VisitEmailTests`, `TimelineTests` in `operations/tests.py`.

---

## 11. Not Yet Built

- Live Gmail calendar read (inbound)
- Edit/delete entire repeat series at once
- Booking METHOD:UPDATE/CANCEL for calendar invite changes