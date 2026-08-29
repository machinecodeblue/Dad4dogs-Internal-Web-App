# Scheduling: Dashboard & agenda

**Load for:** home `/`, month calendar, daily agenda, vaccination compliance cards.  
**Views:** `operations/views/scheduling/dashboard.py`  
**Related:** [`capacity.md`](capacity.md) (occupancy + overlap)

Home screen (`/`) = David’s daily operations view.

---

## Month calendar

- Monday-first grid; prev/next month
- Dot on days with visits; today outlined; selected day filled green
- Click day → `?year=&month=&date=YYYY-MM-DD`
- `year` in `datetime.MINYEAR`…`MAXYEAR`; `month` 1–12. Out-of-range / huge ints fall back to selected day’s month — do not call `date(cal_year, …)` unbounded

---

## Daily agenda

- Compact rows: `Dog · Owner` + time; tap → dog detail
- Checked-in: amber left border + **CHECKED IN** badge only
- Scheduled: green left border, no status badge
- Completed: muted grey, no green COMPLETED badge
- Occupancy = `capacity.count` (distinct dogs). Denominator = Settings **standard** (default 8); insurance max = booking hard stop (default 10). Empty days show **0 / standard**. Always show `N of standard`; **WARNING/OVER** only when not ok
- **Open Check-In** on today
- iCal link in a **Calendar feed** disclosure (not a permanent Quick Links card) — see [`calendar_email.md`](calendar_email.md)

---

## Vaccination compliance cards

Shown **only when count > 0** (no always-on Approved Dogs / Standard Max tiles):

- **Vax Expiring (30d)** — latest validated `expires_at` today…today+30 → `/clients/?vax=expiring`
- **Vax Expired** — latest validated already past → `/clients/?vax=expired`
- Counts from `ClientProfile.objects.vaccination_status_counts()` (one aggregate). Do not N+1 `has_current_vaccination`

---

## Overlap query

Use local `agenda.day_bounds()` overlap (`scheduled_start < day_end AND scheduled_end > day_start`). Canonical detail: [`capacity.md`](capacity.md). Do not use `__date` lookups.

**Tests:** `AgendaTests`, `DashboardViewTests`.
