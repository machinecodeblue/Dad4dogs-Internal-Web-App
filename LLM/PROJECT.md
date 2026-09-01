# Dad4dogs Internal Web App — Tactical Architecture & Project Map

**Owner:** David — Dad4dogs
**Status:** Live Development & Multi-Tenant Architecture
**Audience:** LLM assistants and maintainers

This document is the **tactical entry point and map** for the codebase. Domain specifications live in `LLM/domains/`, code governance lives in `LLM/PHILOSOPHY.md`, and proposal workflows live in `LLM/proposals/` and `LLM/decisions/`.

---

## 1. System Identity & Environment

A **Django 5 application platform** enabling independent pet-care professionals and retirees to run highly controlled, secure, and operationally free dog care operations. Scales from single-operator validation into a partitioned multi-tenant architecture.

| Dimension | Specification |
| --- | --- |
| **Persona** | Independent pet-care operators & retirees. Mobile-first, **one-handed** ergonomics (phone in hand, dogs on leash). |
| **Production Engine** | Free, community-edition **PostgreSQL** (Postgres 18 local dev) for isolation, analytics, and scale. |
| **Data Portability** | Target capability: on-demand standalone pre-populated **SQLite (.sqlite3)** export from Postgres (see `domains/billing/roadmap.md` B5). |
| **Timezone** | `America/Toronto` |
| **Compliance Posture** | SOC 2 Criteria (Security, Confidentiality, Processing Integrity, Privacy). |

---

## 2. Read Order for LLM Sessions

1. **`LLM/PROJECT.md`** (This file) — Tactical map, source tree, live status, and commands.


2. **`LLM/PHILOSOPHY.md`** — Code governance, small file thresholds (~150–200 lines), package conventions, and import layering. Read before writing any code.


3. **`LLM/domains/<domain>.md`** — The Single Source of Truth for the specific domain being modified:


* `customers.md` — Owners, dogs, COI, vaccinations, emergency/vet contacts.


* `scheduling.md` + `scheduling/` — Visits package: booking, check-in, capacity, dashboard, pricing, calendar/email (load one topic at a time).


* `billing.md` + `billing/` — Statements package: compile, email send, unbilled, roadmap (load one topic at a time).


* `services.md` — BusinessService catalog, rate types, behavior rules, capacity exemptions.


* `feed.md` — Staff timeline capture, customer photo feed, speakable URLs, visitor tracking.


* `contacts.md` — Google Contacts CSV import + vCard service package (`services/contacts/`).


* `admin.md` — Business settings, baseline identity, capacity limits (`CapacitySettings`).


* `platform.md` — Dev server, HTTPS, ngrok, PWA, labeled-card UI policy, testing standards.




4. **`LLM/proposals/`** — Read **only** when explicitly instructed to evaluate or refine open proposals. Never implement code directly from proposals.



---

## 3. Domain Package Layout (Code Tree)

All core layers (`models/`, `forms/`, `views/`, `services/`) are organized into modular domain packages with stable `__init__.py` re-exports:

* `operations/models/`: `__init__.py`, `tenant.py` (Workspace root), `base.py` (TenantAwareModel), `business.py` (BusinessProfile + CapacitySettings), `customers.py`, `scheduling.py`, `billing.py`, `services.py`.


* `operations/forms/`: `__init__.py`, `customers.py`, `intake.py`, `scheduling.py`, `services.py`, `business.py`.


* `operations/views/`: `__init__.py` (re-exports subpackages for urls.py), `customers/` (clients, intake, vaccinations, actions), `scheduling/` (dashboard, checkin, visits, timeline, calendar, helpers), `feed/` (private, public, helpers), `billing/` (list, detail, actions, helpers), `services/` (catalog, edit, rules, actions, helpers), `business.py`, `pwa.py`.


* `operations/services/`: `context_tenant.py`, `timeline_media/` (image, video, capture, forwarding), `feed_interactions/` (access, emojis, slugs, reactions, comments, sharing, polling), `contacts/` (schemas, parsers, heuristics, matching, importers, session, vcard), `pricing_engine.py`, `statements/` (compile, format, send, unbilled, weeks), `addresses.py`, `phones.py`, `geolocation.py`, `visit_email.py`, `gmail_send.py`, `gmail_sync.py`.


* Legacy/Scheduling Root Modules: `pricing.py` (legacy fee engine), `capacity/` package (`limits`, `spans`, `engine` — daily occupancy math).


* `operations/templates/operations/`: includes/ (reusable partials) and screen templates.



---

## 4. Root Project Layout
```
Dad4dogs Internal Web App/
├── config/                  # Django settings, root URLs, WSGI/ASGI
├── operations/              # Application business packages (see §3)
├── LLM/                     # Authoritative instruction and specification architecture
│   ├── README.md            # Directory index and reading rules
│   ├── PROJECT.md           # Tactical map (this file)
│   ├── PHILOSOPHY.md        # Code governance and architecture philosophy
│   ├── domains/             # Live domain specifications (single source of truth)
│   ├── proposals/           # Open RFC sandbox
│   └── decisions/           # Historical decisions archive
├── O-Auth Key/              # Gmail API OAuth client secrets & tokens (gitignored)
├── certs/                   # mkcert HTTPS certificates (gitignored)
├── scripts/                 # setup-certs.ps1, run-dev-tunnel.ps1
├── Data samples/            # google_contacts.csv reference fixture
├── oauth_setup.py           # First-time Gmail OAuth interactive desktop consent flow
├── manage.py
└── requirements.txt

```



---

## 5. Implementation Status

| Feature / Subsystem | Status | Reference Specification |
| --- | --- | --- |
| Customer/Dog Split & Pipelines | **Done**<br> | `domains/customers.md`<br> |
| New Client & Dog Intake Wizard | **Done**<br> | `domains/customers.md`<br> |
| Vaccination Expiry Tracking | **Done**<br> | `domains/customers.md`<br> |
| Structured Address Parsing | **Done**<br> | `domains/customers.md`<br> |
| Soft-Hide Dogs (`is_hidden`) | **Done**<br> | `domains/customers.md`<br> |
| Visit Booking (Natural Language) | **Done**<br> | `domains/scheduling/booking.md`<br> |
| Repeat Series Engine | **Done**<br> | `domains/scheduling/booking.md`<br> |
| Dashboard Month & Daily Agenda | **Done**<br> | `domains/scheduling/dashboard.md`<br> |
| Mobile Check-In/Out & Status Guards | **Done**<br> | `domains/scheduling/checkin.md`<br> |
| Booking Confirmation Email (OAuth) | **Done**<br> | `domains/scheduling/calendar_email.md`<br> |
| Google Contacts CSV Import & vCard | **Done**<br> | `domains/contacts.md`<br> |
| Outbound iCal Feed (`/ical/`) | **Done**<br> | `domains/scheduling/calendar_email.md`<br> |
| Contemporaneous Timeline Media | **Done**<br> | `domains/feed.md`<br> |
| Customer Photo Feed (Capability URLs) | **Done**<br> | `domains/feed.md`<br> |
| Feed Reactions, Comments & Share Link | **Done**<br> | `domains/feed.md`<br> |
| Feed Visitor Tracking (`dad4dogs_feed_vid`) | **Done**<br> | `domains/feed.md`<br> |
| PWA Mobile Manifest & Worker | **Done**<br> | `domains/platform.md`<br> |
| PostgreSQL Operational Engine | **Done**<br> | `domains/platform.md`<br> |
| Multi-Tenant Schema Partitioning (Phase 1) | **Done**<br> | `domains/admin.md` |
| `CapacitySettings` Model & Logic Split | **Done**<br> | `domains/admin.md` |
| Services Catalog Scaffolding (Phase 1) | **Done**<br> | `domains/services.md`<br> |
| Weekly Statement Send Automation | **Done**<br> | `domains/billing/email.md`<br> |
| Calendar Inbound `.ics` Sync | **Partial**<br> | `domains/scheduling/calendar_email.md`<br> |
| Services Phase 2 (Engine Cutover) | **Done**<br> | `domains/services.md`<br> |
| Default Tenant QuerySet / Middleware (Phase 2) | **Planned**<br> | `domains/admin.md` |
| Portable SQLite Operator Export | **Planned**<br> | `domains/billing/roadmap.md` (B5)<br> |
| Multi-Tenant Auth & Membership | **Planned**<br> | `domains/admin.md` |

---

## 6. Quick Commands

* **Database & Setup:** `pip install -r requirements.txt`, `python manage.py migrate`, `python manage.py createsuperuser`.


* **Run HTTPS Dev Server:** `python manage.py runserver_https 9000`.


* **Gmail OAuth Authentication:** `python oauth_setup.py`, `python manage.py gmail_auth --test you@email.com`.


* **Test Suite:** `python manage.py test operations`.


* **Public Domain Variable:** Set `$env:PUBLIC_SITE_URL = "[https://your-tunnel-domain.ngrok-free.app](https://your-tunnel-domain.ngrok-free.app)"` to test feed sharing.



---

## 7. RFC Protocol: Proposals vs. Decisions

* **`LLM/proposals/` is an RFC Sandbox:** New features, major schema alterations, or cross-domain refactors are drafted here first. LLMs may read across all `domains/` files to evaluate impacts and debate tradeoffs. **No code or migrations are executed from this directory**.


* **Acceptance Protocol:** When David accepts a proposal, live architectural rules and schema changes are written into the respective `LLM/domains/<domain>.md` file(s). The proposal is moved to `LLM/decisions/` with a standardized header indicating Status (`Accepted`, `Rejected`, or `Partial`), Summary (what landed vs what was left), and Live Spec Location (`domains/*.md`). The draft is removed from `LLM/proposals/` so the open queue stays clean.