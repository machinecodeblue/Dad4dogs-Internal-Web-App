# Dad4dogs Internal Web App — LLM Project Guide

**Owner:** David — Dad4dogs  
**Last updated:** July 2026  
**Audience:** LLM assistants and future maintainers

This is the **single entry point** for understanding this codebase. Domain-specific detail lives in separate files — read those when working in that area.

---

## 1. What This App Is

A **Django 5 monolith** for David's single-user dog boarding operation (~25 repeat clients).

| Principle | Detail |
|-----------|--------|
| **Persona** | David-only, mobile-first (phone via ngrok during dev) |
| **Database** | SQLite |
| **Timezone** | `America/Toronto` |
| **Scale** | ~25 dogs; capacity warns at 9+, blocks above 10/day (insurance ceiling) |
| **Architecture** | One app (`operations`) split by **domain packages** — never monolithic 500-line files |

**Core domains:**

| Domain | Covers |
|--------|--------|
| **Customers** | Owners, dogs, COI, vaccinations, Google Contacts import |
| **Scheduling** | Visits, repeat series, dashboard, check-in/out, pricing, calendar |
| **Billing** | Weekly statements, checkout fees (pricing engine lives in scheduling) |
| **Admin** | Business baseline — identity, address, hours, phone numbers, documents (planned) |

---

## 2. Read Order for LLM Sessions

1. **This file** (`PROJECT.md`) — context and file map
2. **Domain file** for the area you are changing:
   - `customers.md` — owners, dogs, COI, vax, contacts
   - `scheduling.md` — visits, agenda, check-in, pricing, email confirmations
   - `billing.md` — statements
   - `admin.md` — business settings, baseline contact info, documents (planned)
3. **`platform.md`** — dev server, HTTPS, ngrok, Gmail OAuth, UI conventions, testing

Do **not** change pricing tiers, capacity ceilings, or pipeline stages unless David explicitly asks.

---

## 3. Domain Package Layout (Code)

Code is organized by domain in **models**, **forms**, and **views**:

```
operations/
├── models/
│   ├── __init__.py       # re-exports all models
│   ├── customers.py      # CustomerOwner, ClientProfile, VaccinationRecord
│   ├── scheduling.py     # VisitSeries, Visit, PendingCalendarEvent
│   ├── billing.py        # AccountStatement
│   └── business.py       # BusinessProfile (singleton)
├── forms/
│   ├── __init__.py
│   ├── customers.py      # CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
│   ├── scheduling.py     # VisitForm
│   └── business.py       # BusinessProfileForm
├── views/
│   ├── __init__.py       # urls.py imports from here
│   ├── customers.py      # clients, dogs, COI, vax, contacts
│   ├── scheduling.py     # dashboard, check-in, visits, calendar, iCal
│   ├── billing.py        # statements
│   └── business.py       # business_settings
├── services/             # business logic — prefer adding here over bloating views
├── pricing.py            # tiered fee engine (scheduling domain)
├── capacity.py           # daily dog count guards (scheduling domain)
└── templates/operations/
```

**Rule for new code:** add to the matching domain file. If a file grows past ~200 lines, split further within that domain — do not merge domains.

---

## 4. Project Tree (source only)

Regenerate with: `tree /F /A > project_schema.txt` from project root.

```
Dad4dogs Internal Web App/
├── config/                 # Django settings, root URLs
├── operations/             # All business logic (see §3)
├── LLM/                    # Instruction sets (this folder)
├── O-Auth Key/             # Gmail OAuth credentials + token (gitignored)
├── certs/                  # mkcert HTTPS certs (gitignored)
├── scripts/                # setup-certs.ps1, run-dev-tunnel.ps1
├── Data samples/           # google_contacts.csv reference
├── oauth_setup.py          # One-time Gmail OAuth browser flow
├── manage.py
└── requirements.txt
```

---

## 5. Business Rules Summary (do not change casually)

### Pipeline (per dog)
Inquiry → Meet & Greet → Evaluation → Approved

### Pricing (CAD, at checkout)
| Tier | Rule | Rate |
|------|------|------|
| Short | ≤ 4 hours (not overnight) | $15 |
| Daytime | ≤ 12 hours (not overnight) | $25 |
| Overnight | Crosses 11 PM–4 AM **or** starts before 4 AM | $37.50 |

Overnight is evaluated **before** hour tiers. Multi-day: each full 24h = Overnight; remainder priced separately.

### Customer vs dog (critical)
- **Customer** (`CustomerOwner`) = one per `owner_email`; owns COI
- **Dog** (`ClientProfile`) = `owner_email` + `dog_name`; owns pipeline, visits, vaccinations
- A customer may have **zero dogs** until David adds one
- Never invent a dog from the owner's first name on import

---

## 6. Implementation Status

| Feature | Status |
|---------|--------|
| Customer/dog split UI | Done |
| Pipeline per dog, COI per customer | Done |
| Visit booking (natural-language Start/End) | Done |
| Repeat series (daily/weekly/weekdays/monthly) | Done |
| Dashboard month calendar + daily agenda | Done |
| Mobile check-in/out + auto pricing | Done |
| Booking confirmation email (Gmail OAuth) | Done |
| Google Contacts selective import + vCard | Done |
| iCal outbound `/ical/` | Done |
| HTTPS dev server + ngrok | Done |
| Business settings (`/settings/`) | Done — identity, address, hours, phones |
| Business document uploads (COI, etc.) | Not started |
| Calendar inbound `.ics` import command | Partial — file-based, not live Gmail |
| Weekly statement **email send** | Partial — generates + formats; send not wired |
| GoDaddy inquiry parsing | Not started |
| Per-dog day notes (replaces WhatsApp) | Planned |
| e-Transfer automation | Not started |

---

## 7. Quick Commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver_https 9000          # local HTTPS
ngrok http https://127.0.0.1:9000              # mobile tunnel
python oauth_setup.py                          # first-time Gmail token
python manage.py gmail_auth --test you@email.com
python manage.py test operations
```

---

## 8. LLM Session Checklist

1. Identify the **domain** before editing (customers / scheduling / billing / admin / platform).
2. Open the matching `LLM/<domain>.md` file.
3. Keep **mobile-first** UX — no desktop-only patterns.
4. Visit booking stays **two free-text fields** (Start/End) — no multi-step pickers.
5. No bulk Google contact import without preview + checkboxes.
6. Extend `operations/services/` for new business logic.
7. Add tests in `operations/tests.py` for pricing, capacity, forms, or imports you touch.
8. Never commit `O-Auth Key/`, `certs/`, or live client PII.

---

## 9. Domain Instruction Files

| File | Contents |
|------|----------|
| [`customers.md`](customers.md) | Owners, dogs, COI, vaccinations, contacts import |
| [`scheduling.md`](scheduling.md) | Visits, repeat, dashboard, check-in, pricing, calendar, booking email |
| [`billing.md`](billing.md) | Weekly statements, checkout totals |
| [`admin.md`](admin.md) | Business settings, baseline contact info, documents |
| [`platform.md`](platform.md) | Dev environment, HTTPS, ngrok, Gmail, UI, testing |