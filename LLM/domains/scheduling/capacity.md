# Scheduling: Capacity

**Load for:** occupancy math, blocked bookings, `skip_capacity`, catalog exemptions.  
**Code package:** `operations/capacity/` (`limits.py`, `spans.py`, `engine.py`, `__init__.py`)  
**Related:** [`../admin.md`](../admin.md) (CapacitySettings UI), [`../services.md`](../services.md), [`booking.md`](booking.md)

---

## Purpose

- **Standard** — comfortable daily count (dashboard `N / standard`; warn when over)
- **Insurance max** — hard stop for **new** bookings

Both live on `CapacitySettings` for the active workspace (`/settings/`). Defaults 8 / 10 if missing. Do not hardcode; use `assess_capacity` / `capacity_limits()`.

`capacity_limits()` — single query (`values_list`) on the hot path.

---

## Behaviour

| Count | Behaviour |
| --- | --- |
| ≤ standard | OK — `N / standard` |
| standard < count ≤ insurance | Warning |
| > insurance | Block (new bookings) |

Counts distinct `client_id` with overlapping `scheduled` / `checked_in` / `completed` visits that **occupy facility capacity**. Keep tenant-scoped Visit indexes on `status`, `scheduled_start`, `scheduled_end`.

### Catalog Exemption

- **Meet & Greet** (`capacity_exempt=True`): does **not** count in dashboard/check-in occupancy (`count_dogs_on_day` / `assess_capacity` exclude `business_service__capacity_exempt=True`). Booking gate also skips via `check_visit_capacity`.
- **Initial Evaluation** and boarding: **do** count toward facility capacity.
- `check_visit_capacity(visit)` returns ok when `capacity_exempt` **or** `target_category != 'DOG'`.
- **Same-dog overlap still runs** for M&G (a dog cannot double-book themselves) — overlap uses visits without the facility-capacity exclude.

---

## Overlap Query (Canonical)

`scheduled_start < day_end` AND `scheduled_end > day_start` with **local** midnight bounds (`day_bounds()` / `agenda.day_bounds()`). Do **not** use `scheduled_start__date` / `scheduled_end__date` (wrong for aware datetimes / overnight).

Same pattern for capacity, check-in, feed activity, timeline eligibility, dashboard.

---

## Implementation Notes (`operations/capacity/`)

- `limits.py` — `capacity_limits()`, `format_capacity_status()`
- `spans.py` — `as_local()`, `day_bounds()`, `capacity_span_dates()`
- `engine.py` — `overlapping_visits()`, `overlapping_dog_visit()`, `count_dogs_on_day()`, `assess_capacity()`, `daily_dog_counts()`, `check_visit_capacity()`
- `count_dogs_on_day` — `Count('client_id', distinct=True)` in SQL; if `include_client_id`, aggregate + add 1 only when missing
- Day windows via `timezone.get_current_timezone()` (`America/Toronto`) — not host OS zone
- Span dates via `as_local()` / `timezone.localtime()` after `make_aware` if naive — never `.tzinfo` on naive
- Exact local midnight `scheduled_end` belongs to the **prior** day only (`scheduled_end > day_start`)
- Multi-day booking: one `daily_dog_counts` query for `[start_day, end_day]` — do not N+1 `assess_capacity` per day
- Forms call `check_visit_capacity` in `VisitForm.clean()` so a full day fails before any `VisitSeries` write

---

## When Capacity Runs

Capacity is a **booking** rule, not a day-of-ops lock:

| Write | `full_clean` / `check_visit_capacity`? |
| --- | --- |
| `Visit.save()` no `update_fields` (create, edit times, clone, admin) | Yes (unless catalog-exempt) |
| `VisitForm.save_all()` after valid `clean()` | `full_clean` yes; capacity **no** (`skip_capacity=True`). Edits: `update_fields` start/end/notes/`business_service`/`updated_at` |
| `update_fields` includes start/end/`client` | Yes |
| `check_in()` / `check_out()` | **No** |
| Check-in **view** | Still `assess_capacity` for message; model save does not re-block |

Do not `full_clean()` from check-in/out. Do not pass `skip_capacity=True` from views/clone/admin — only `VisitForm.save_all()`.

**Tests:** `VisitCapacitySaveTests`, `CapacityTimezoneTests`, settings form/dashboard capacity display tests.