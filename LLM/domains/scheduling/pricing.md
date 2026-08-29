# Scheduling: Pricing

**Load for:** checkout fees, fee correction, catalog vs legacy path.  
**Code:** `operations/pricing.py`, `operations/services/pricing_engine.py`, `Visit._price_stay`  
**Related:** [`../services.md`](../services.md), [`../billing.md`](../billing.md), [`checkin.md`](checkin.md)

Classic tier table: `PROJECT.md` §5.

---

## Paths

| Visit | Fee function |
| --- | --- |
| `business_service` null (legacy) | `operations.pricing.calculate_fee(arrival, departure)` |
| `business_service` set | `pricing_engine.calculate_service_fee(service, arrival, departure)` via `Visit._price_stay` |

`check_out()` and completed `update_actual_times()` both go through `_price_stay()`.

### Catalog engine behaviour

- **DOG boarding** (not capacity-exempt): overnight-first parity with `pricing.py`; breakdown tiers annotated with service name/slug
- **Other / capacity-exempt:** flat `service.base_rate` for the stay window

---

## Rules

- Return `(Decimal total, list[line_items])`
- Line item amounts are **strings** (JSONField-safe)
- Legacy path: `is_overnight_segment()` before hour tiers; multi-day full 24h blocks = Overnight, remainder priced separately
- New bookings require an active `BusinessService` (see [`booking.md`](booking.md)); legacy null still checks out via `pricing.py`
- Do not re-implement overnight tiers in views

**Tests:** `PricingEngineTests`, `VisitCheckOutTests` — keep green when touching fee paths.
