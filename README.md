# Dad4dogs Internal Web App

A Django monolith for David's single-user dog boarding operations at **Dad4dogs**. Built for ~25 repeat clients with mobile-first check-in, automated pricing, calendar sync, and weekly billing statements.

## Tech Stack

- **Django 5** + **SQLite**
- Mobile-optimized UI (designed for ngrok tunnel access)
- Read-only iCal feed for Google Calendar subscription

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create your login (David)
python manage.py createsuperuser

# Start the dev server (port 9000 — 8000 may already be in use)
python manage.py runserver 9000

# Optional: expose via ngrok for mobile access
ngrok http 9000
```

Open **http://127.0.0.1:9000/** for the dashboard. Admin panel at **/admin/**.

## Core Features

| Feature | Description |
|---------|-------------|
| **Client Pipeline** | Inquiry → Meet & Greet → Evaluation → Approved |
| **Mobile Check-In** | One-tap arrival/departure logging |
| **Capacity Guards** | Warn at 9–10 dogs/day; block above 10 (insurance ceiling) |
| **Pricing Engine** | Short ($15) / Daytime ($25) / Overnight ($37.50) with multi-day logic |
| **Visit Duplication** | Clone past visit times to a new date in one click |
| **iCal Feed** | Subscribe `/ical/` in Google Calendar |
| **Calendar Import** | `python manage.py import_calendar path/to/export.ics` |
| **Day Notes (planned)** | Per-dog contemporaneous notes during active visits |
| **Weekly Statements** | `python manage.py generate_statements` |

## Google Calendar Setup

1. Subscribe to your iCal feed: `https://your-domain/ical/`
2. Export incoming Google Calendar events as `.ics` periodically
3. Import with: `python manage.py import_calendar calendar.ics`
4. Review pending events at `/calendar/pending/`

## Pricing Rules

- **Overnight** ($37.50): Stay crosses 11 PM–4 AM window OR begins before 4 AM — evaluated *before* hour tiers
- **Short Visit** ($15): ≤ 4 hours (when not overnight)
- **Daytime Visit** ($25): ≤ 12 hours (when not overnight)
- **Multi-day**: Each full 24h block = Overnight; remainder priced separately

## Owner

**David** — Dad4dogs