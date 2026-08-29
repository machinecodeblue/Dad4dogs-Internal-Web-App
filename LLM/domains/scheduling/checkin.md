# Scheduling: Check-in / check-out

**Load for:** mobile check-in/out, status guards, actual-time correction, double-tap safety.  
**Related:** [`pricing.md`](pricing.md), [`../feed.md`](../feed.md)  
**Views:** `operations/views/scheduling/checkin.py`

---

## Mobile check-in (`/checkin/`)

- Lists today’s overlapping **scheduled + checked-in** visits (`day_bounds`, not `__date__`), plus **Checked out today** for overlapping **completed** visits (late tap corrections)
- Card: dog, owner, tap-to-call (emergency vet if present, else clinic). No green OK badges.
- Scheduled: **Check In**. Checked-in: **Log Moment** + **Check Out**. Time correction: compact `datetime-local` + outline **Update time(s)** (not a third primary CTA)
- Capacity count always; WARNING/OVER only when not ok
- Check-in → `actual_arrival = now`, `checked_in`; check-out → `actual_departure = now`, `_price_stay()`, `completed`
- **Meet & Greet check-out:** redirects to `/visits/<id>/meet-greet-outcome/` (notes + **Pass** / **Decline**) — only Pass opens Evaluation
- **Initial Evaluation check-out:** redirects to `/visits/<id>/evaluation-outcome/` (notes + Approve / Reject / Further)
- Capacity re-checked at check-in (view message); model save does not re-block
- **Owner feed activity** polls `/checkin/feed-activity/` every 15s

Overlap day bounds: see [`capacity.md`](capacity.md) / [`dashboard.md`](dashboard.md).

---

## Correcting actual arrival / departure

Tap records `timezone.now()`; David corrects Visit row fields (not timeline events):

| Status | Editable fields | Fee |
| --- | --- | --- |
| `checked_in` | `actual_arrival` only | unchanged |
| `completed` | arrival + departure | recalculate via `_price_stay()` |

`Visit.update_actual_times(…)` · `POST /visits/<id>/actual-times/`. Parse `datetime-local` as America/Toronto. Scheduled/cancelled rejected. `update_fields` save (no capacity). Do **not** change status here.

Weekly statements pick up corrected `calculated_fee` on next `generate_weekly_statements` run.

---

## Status guards (idempotent transitions)

Double-tap / stale POST must **not** overwrite arrival, re-price, or complete an unchecked visit.

| Method | Allowed from | On success | Otherwise |
| --- | --- | --- | --- |
| `check_in()` | `scheduled` only | arrival = now, `checked_in` | `ValidationError` — no writes |
| `check_out()` | `checked_in` **and** `calculated_fee` null | departure = now, `_price_stay()`, `completed` | `ValidationError` — no writes |
| `update_actual_times()` | `checked_in` or `completed` | correct times; re-fee if completed | `ValidationError` — no writes |

Views catch `ValidationError`, flash, redirect to `/checkin/` — never 500.

Refused transition = error, not silent success (unless David asks otherwise). Template hides wrong buttons; guards are for stale POSTs.

`check_out()` `refresh_from_db` before pricing. If `calculated_fee` already set, raise — even if status still says `checked_in`.

`check_in` / `check_out` / `update_actual_times` use `update_fields` so capacity is **not** re-run (dog already on site).

**Tests:** `VisitCheckOutTests`, `VisitCheckInOutViewTests`, `VisitCapacitySaveTests` — keep green when touching these paths.

---

## Staff timeline (pointer)

While `checked_in`, David logs photo/video at `/visits/<id>/timeline/`. Forms: `forms/scheduling/timelines.py`. Templates: `visit_timeline.html` shell + `components/timeline/` (`capture_form`, `moment_card`, `forward_panel`). Full rules, customer feed, security: [`../feed.md`](../feed.md). Services: `timeline_media/`, `feed_interactions/`.
