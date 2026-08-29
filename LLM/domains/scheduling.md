# Domain: Scheduling

**Covers:** visits, repeat series, dashboard agenda, check-in/out, pricing, capacity, calendar sync, booking confirmation email.

This domain is a **documentation package**. Deep rules live under [`scheduling/`](scheduling/) — do **not** load every topic file by default.

## Load order for scheduling work

1. This shim (orientation) **or** [`scheduling/index.md`](scheduling/index.md)
2. **Only** the topic file for the task (see table)

| Task | File |
| --- | --- |
| Package paths / models / URL map | [`scheduling/index.md`](scheduling/index.md) |
| Booking / repeat / clone | [`scheduling/booking.md`](scheduling/booking.md) |
| Check-in / out / time fix | [`scheduling/checkin.md`](scheduling/checkin.md) |
| Capacity / overlap blocks | [`scheduling/capacity.md`](scheduling/capacity.md) |
| Dashboard / agenda | [`scheduling/dashboard.md`](scheduling/dashboard.md) |
| Checkout fees | [`scheduling/pricing.md`](scheduling/pricing.md) |
| Email / iCal / inbound calendar | [`scheduling/calendar_email.md`](scheduling/calendar_email.md) |

**Also:** customer feed → [`feed.md`](feed.md); catalog offerings → [`services.md`](services.md).

**Code packages:** `operations/models/scheduling/`, `operations/forms/scheduling/`, `operations/views/scheduling/` (see index for trees).
