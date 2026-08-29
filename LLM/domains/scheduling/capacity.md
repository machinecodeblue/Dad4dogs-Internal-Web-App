# Scheduling: Capacity

**Load for:** occupancy math, blocked bookings, `skip_capacity`, catalog exemptions.  
**Code:** `operations/capacity.py`  
**Related:** [`../admin.md`](../admin.md) (CapacitySettings UI), [`../services.md`](../services.md), [`booking.md`](booking.md)

---

## Purpose

- **Standard** — comfortable daily count (dashboard `N / standard`; warn when over)
- **Insurance max** — hard stop for **new** bookings

Both live on `CapacitySettings` for the active workspace (`/settings/`). Defaults 8 / 10 if missing. Do not hardcode; use `assess_capacity` / `capacity_limits()`.

`capacity_limits()` — one JOIN/`values_list` on the hot path.

---

## Behaviour

| Count | Behaviour |
| --- | --- |
| ≤ standard | OK — `N / standard` |
| standard < count ≤ insurance | Warning |
| > insurance | Block (new bookings) |

Counts distinct `client_id` with overlapping `scheduled` / `checked_in` / `completed` visits. Keep tenant-scoped Visit indexes on `status`, `scheduled_start`, `scheduled_end`.

### Catalog exemption

`check_visit_capacity(visit)` returns ok (count 0) when `business_service` is set and (`capacity_exempt` **or** `target_category != 'DOG'`). **Same-dog overlap still runs** in `Visit.clean()` / form clean.

---

## Overlap query (canonical)

`scheduled_start < day_end` AND `scheduled_end > day_start` with **local** midnight bounds (`agenda.day_bounds()` / `_day_bounds`). Do **not** use `scheduled_start__date` / `scheduled_end__date` (wrong for aware datetimes / overnight).

Same pattern for capacity, check-in, feed activity, timeline eligibility, dashboard.

---

## Implementation notes

- `count_dogs_on_day` — `Count('client_id', distinct=True)` in SQL; if `include_client_id`, aggregate + add 1 only when missing
- Day windows via `timezone.get_current_timezone()` (`America/Toronto`) — not host OS zone
- Span dates via `_as_local()` / `timezone.localtime()` after `make_aware` if naive — never `.tzinfo` on naive
- Exact local midnight `scheduled_end` belongs to the **prior** day only (`scheduled_end > day_start`)
- Multi-day booking: one `_daily_dog_counts` query for `[start_day, end_day]` — do not N+1 `assess_capacity` per day
- Forms call `check_visit_capacity` in `VisitForm.clean()` so a full day fails before any `VisitSeries` write

---

## When capacity runs

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
