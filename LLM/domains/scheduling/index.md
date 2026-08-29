# Domain: Scheduling (index)

**Covers:** visits, repeat series, dashboard agenda, check-in/out, pricing, capacity, calendar sync, booking confirmation email.

**Do not load every file in this folder by default.** Start here — or the thin domain entry [`../scheduling.md`](../scheduling.md) — then open **only** the topic file for the task.

| Task | Load |
| --- | --- |
| Booking / repeat / clone | [`booking.md`](booking.md) |
| Check-in / out / time fix | [`checkin.md`](checkin.md) |
| Capacity / overlap booking block | [`capacity.md`](capacity.md) |
| Dashboard / agenda | [`dashboard.md`](dashboard.md) |
| Fees at checkout | [`pricing.md`](pricing.md) |
| Email / iCal / pending calendar | [`calendar_email.md`](calendar_email.md) |
| Package paths / models map | this file |

**Customer feed:** [`../feed.md`](../feed.md)  
**Catalog services:** [`../services.md`](../services.md)

---

## Code packages

- `operations/models/scheduling/` — `visits`, `series`, `media`, `timeline`, `interactions`, `calendar`
- `operations/forms/scheduling/` — `visits.py`, `timelines.py`
- `operations/views/scheduling/` — `dashboard`, `checkin`, `visits`, `timeline`, `calendar`, `helpers`
- Root: `operations/pricing.py`, `operations/capacity.py`
- Services: `timeline_media/`, `feed_interactions/`, `pricing_engine.py`, `agenda.py`, `datetime_parse.py`, `visit_repeat.py`, `visit_email.py`, `gmail_send.py`, `ical_feed.py`, `gmail_sync.py`, `timeline_visits.py`, `geolocation.py`

Do **not** recreate monoliths `operations/models/scheduling.py` or `operations/forms/scheduling.py`.

---

## Data model

All models inherit from `TenantAwareModel` (`tenant` FK).

| Model | Submodule | Purpose |
| --- | --- | --- |
| `Visit` | `visits.py` | Stay; status guards; pricing via `_price_stay` |
| `VisitSeries` | `series.py` | Recurring visits from one booking |
| `TimelineMediaAsset` | `media.py` | Immutable photo/video capture |
| `VisitTimelineEvent` | `timeline.py` | Links asset ↔ visit; forwards |
| `MediaReaction` / `MediaComment` / `SharedMediaLink` | `interactions.py` | Feed social (see `feed.md`) |
| `PendingCalendarEvent` | `calendar.py` | Inbound calendar awaiting review |

### Visit statuses

`scheduled` → `checked_in` → `completed` (or `cancelled`)

Transitions only via `check_in()` / `check_out()` / `update_actual_times()` — details in [`checkin.md`](checkin.md).

### Visit key fields

- `scheduled_start`, `scheduled_end`
- `business_service` — required on **new** bookings; null OK on legacy
- `actual_arrival`, `actual_departure`, `calculated_fee`, `fee_breakdown`
- `confirmation_email_sent_at`, `series`, `series_position`

### Indexes (`Visit.Meta`)

| Name | Fields |
| --- | --- |
| `visit_tenant_start_idx` | `tenant`, `scheduled_start` |
| `visit_tenant_end_idx` | `tenant`, `scheduled_end` |
| `visit_tenant_status_idx` | `tenant`, `status` |

Do not drop these. Prefer tenant-prefixed names over old `visit_scheduled_*` from migration `0016`.

### Package trees

```
operations/models/scheduling/   # visits, series, media, timeline, interactions, calendar
operations/forms/scheduling/    # visits.py, timelines.py
operations/views/scheduling/    # dashboard, checkin, visits, timeline, calendar, helpers
```

Imports: `from operations.models.scheduling import Visit`, `from operations.forms.scheduling import VisitForm`.

---

## URLs (compact)

Wrong HTTP verbs → **405**. Full behavior lives in topic files.

| Path | Methods | Topic |
| --- | --- | --- |
| `/` | GET | [`dashboard.md`](dashboard.md) |
| `/checkin/`, check-in/out/actual-times | GET/POST | [`checkin.md`](checkin.md) |
| `/dogs/<id>/visits/add/`, edit/delete, parse-datetime | GET/POST | [`booking.md`](booking.md) |
| `/visits/<id>/send-confirmation/` | POST | [`calendar_email.md`](calendar_email.md) |
| `/visits/<id>/timeline/…` | GET/POST | [`checkin.md`](checkin.md) → `feed.md` |
| `/calendar/pending/…`, `/ical/` | GET/POST | [`calendar_email.md`](calendar_email.md) |

---

## Tests

`VisitFormTests`, `DatetimeParseTests`, `AgendaTests`, `DashboardViewTests`, `PricingEngineTests`, `VisitCheckOutTests`, `VisitCheckInOutViewTests`, `VisitCapacitySaveTests`, `PendingEventApproveTests`, `VisitIndexTests`, `VisitCloneToDateTests`, `VisitEmailTests`, `TimelineTests` in `operations/tests.py`.

## Not yet built

- Live Gmail calendar read (inbound)
- Edit/delete entire repeat series at once
- Booking METHOD:UPDATE/CANCEL
- Billing service-aware statement lines (see `services.md` Phase 3)

## LLM packaging rules

1. Prefer package paths; re-export via `__init__.py`.
2. New bookings require active `BusinessService`; legacy null still checks out via `pricing.py`.
3. Linked-service fees → `pricing_engine.py`; facility capacity skips exempt / non-DOG; same-dog overlap always.
4. Status transitions only via model methods.
5. Timeline forms in `forms/scheduling/timelines.py`; media I/O in `timeline_media/`; social in `feed_interactions/` / `feed.md`.
