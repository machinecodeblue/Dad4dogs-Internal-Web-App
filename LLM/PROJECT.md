### Dad4dogs Internal Web App — LLM Project Guide

**Owner:** David — Dad4dogs
**Last updated:** August 2026
**Audience:** LLM assistants and future maintainers 

This is the **single entry point** for understanding this codebase. Domain-specific detail lives in separate files — read those when working in that area. 

### 1. What This App Is

A **Django 5 application service platform** designed to enable independent pet-care professionals and retirees to run highly controlled, secure, and operationally free dog sitting businesses. It scales fluidly from a localized validation proof-of-concept into a robust, multi-tenant software architecture engineered for eventual enterprise acquisition. 

Principle 

Detail 


| **Dimension** | **Specification** |
| :--- | :--- |
| **Persona** | Independent pet-care operators & retirees. Mobile-first, **one-handed** ergonomics (phone in hand, dogs on leash). |
| **Production Engine** | Free, community-edition **PostgreSQL** to handle multi-tenant isolation, enterprise analytics, search concurrency, and scale. |
| **Data Portability** | **Target capability (not built yet):** operators will generate a standalone pre-populated **SQLite (.sqlite3)** of their data context from Postgres. Keep schemas relationally clean for that pipeline (see `billing.md` section 8). |
| **Timezone** | America/Toronto |
| **Scale & Compliance** | Engineered out-of-the-box for **SOC 2 Compliance** (Security, Confidentiality, Processing Integrity, and Privacy Criteria). |


**Core domains:** 

| Domain | Covers |
|--------|--------|
| **Customers** | Owners, dogs, COI, vaccinations, Google Contacts import |
| **Scheduling** | Visits, repeat series, dashboard, check-in/out, pricing, calendar |
| **Billing** | Weekly statements, checkout fees (pricing engine lives in scheduling); portable SQLite export **future** |
| **Admin** | Business baseline — identity, address, hours, phone numbers, documents (planned) |
| **Feed** | Staff timeline capture + customer photo feed (secret link, no password; visitor cookie `dad4dogs_feed_vid` today — see `feed.md`) |

---

## 2. Read Order for LLM Sessions

1. **This file** (PROJECT.md) — context and file map
2. **applicationphilosophy.md** — how we shape code (small files, domain packages, no god modules). Read before structural or large feature work.
3. **Domain file** for the area you are changing: 

  * customers.md — owners, dogs, COI, vax, contacts
  * scheduling.md — visits, agenda, check-in/out guards, pricing, email confirmations
  * billing.md — statements; portable SQLite export (future)
  * admin.md — business settings, baseline contact info, documents (planned)
  * feed.md — timeline capture, customer photo feed, speakable URLs, visitor fingerprinting
  * services.md — **next major build** (configurable services/pricing design). Not live; do not implement until David asks.
4. **platform.md** — dev server, HTTPS, ngrok, Gmail OAuth, PWA, **detail-screen labeled-card policy**, testing. Any customer/dog/list/dashboard/check-in template change must follow those rules.

Do **not** treat Proposed work/ or Decisions/ as the live spec. Open proposals are evaluation-only; decided notes are history. Standing rules live in this file, `applicationphilosophy.md`, and the domain markdown. 

Do **not** change pricing tiers, pipeline stages, or visit status guards unless David explicitly asks. Daily capacity (standard + insurance max) is edited on **Settings** — do not hardcode 8/10 in templates or capacity.py checks. 

### 3. Domain Package Layout (Code)

All core layers (views, models, forms) must be organized as **modular Python packages**: 

```
operations/
├── models/
│   ├── __init__.py      # Re-exports all models
│   ├── customers.py     # CustomerOwner, ClientProfile, VaccinationRecord
│   ├── scheduling.py    # VisitSeries, Visit, TimelineMediaAsset, VisitTimelineEvent, MediaComment, MediaReaction
│   ├── billing.py       # AccountStatement
│   ├── tenant.py        # Workspace (thin tenant root)
│   ├── base.py          # TenantAwareModel
│   └── business.py      # BusinessProfile + CapacitySettings (1:1 to Workspace)
├── forms/
│   ├── __init__.py      # Re-exports all forms
│   ├── customers.py     # CustomerOwnerForm, DogProfileForm, VaccinationRecordForm
│   ├── intake.py        # IntakeWizardForm (new client & dog)
│   ├── scheduling.py    # VisitForm, TimelineMomentForm, TimelineForwardForm
│   └── business.py      # BusinessProfileForm
├── views/
│   ├── __init__.py      # urls.py imports from here (re-exports all sub-packages)
│   ├── customers/       # Domain package for customer workflows
│   │   ├── __init__.py  # Re-exports clients, intake, vaccinations, actions
│   │   ├── clients.py   # client_list, customer/dog detail, edits
│   │   ├── intake.py    # client_intake, client_create, dog_create_customer
│   │   ├── vaccinations.py # dog_vaccinations, add_vaccination, validate_vaccination
│   │   ├── contacts.py  # contact sync/export (legacy)
│   │   └── actions.py   # dog_hide, dog_unhide, update_coi, pipeline, feed regenerate
│   ├── scheduling/      # dashboard, checkin, visits, timeline, calendar, helpers
│   │   ├── __init__.py  # Re-exports public view callables
│   │   ├── dashboard.py, checkin.py, visits.py, timeline.py, calendar.py, helpers.py
│   ├── feed/            # Customer photo feed + public share
│   │   ├── __init__.py
│   │   ├── private.py   # customer_feed, react, comment, redirect (secret URL)
│   │   ├── public.py    # public share / react / comment / download
│   │   └── helpers.py
│   ├── billing.py       # Statements list/detail (portable export future — not here yet)
│   ├── business.py      # Business settings
│   └── pwa.py           # manifest.webmanifest, sw.js
├── services/            # Pure business logic — prefer adding here over bloating views
│   ├── timeline_media.py, timeline_visits.py, geolocation.py
│   ├── addresses.py, phones.py, feed_slugs.py, feed_access.py
│   ├── feed_interactions.py, feed_emojis.py, share_preview.py, statements.py
│   ├── context_tenant.py # get_active_workspace() single-operator bridge
│   └── visit_email.py, gmail_send.py, gmail_sync.py
├── pricing.py           # Tiered fee engine (scheduling domain)
├── capacity.py          # Daily dog count guards (scheduling domain)
└── templates/operations/
├── includes/            # Reusable partials (navigation, social widgets, share sheets)
└── 
```

**Rule for new code:** add to the matching domain file. If a file grows past ~150 lines, split further within that domain directory package — do not merge domains. 

---
### 4.1 Project Tree (source only)

Regenerate with: tree /F /A > project_schema.txt from project root. 

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
### 4.2 LLM Coding & Architectural Rules

### Rule A: Directory Packages & Max File Length

* Full philosophy (why, audit habit, LLM expectations): **`applicationphilosophy.md`**.
* If any file exceeds ~150–200 lines, split it into submodules within its domain directory package — proactively, before it becomes a god module.
* Always expose public functions, models, and forms in `__init__.py` so that external imports and urls.py routes remain uninterrupted. Pattern: `views/scheduling/`, `views/customers/`, `views/feed/`.

### Rule B: Template Modularity & Explicit Context Wiring

* Base templates (base.html, customer_base.html) must remain minimal shells; navigation, alert messaging, PWA dialogs, and modals must live in templates/operations/includes/.
* When including reusable action components (e.g., moment_interactions.html), **explicitly map all required endpoints** (react_url, comment_url, asset_id, etc.) via {% include "..." with ... %}. Never rely on implicit context or pass unmapped parent objects.

### Rule C: Multi-Tenancy Data Separation & Portability

* **Tenant Scope Isolation**: Data layers must partition access based on the active user scope. Global un-filtered database iterations are forbidden to safeguard customer confidentiality.
* **Portability Pipeline**: Feature updates must map cleanly to relational schema tables, maintaining baseline architectural compatibility for on-demand conversion into download-ready standalone SQLite binaries.

### Rule D: Abuse Defense and Non-Repudiation (SOC 2)

* Public-facing workflows without passwords (photo feed, comments) must identify visitors. **Live:** cookie `dad4dogs_feed_vid` (`feed.md`). **Target:** stronger `visitor_hash` (SHA-256 of IP + User-Agent + cookie) — not implemented yet.
* Raw PII must never leak into application logging systems, tracing blocks, or error console feeds.

### Rule E: Visit Status & Transition Guards

* Transitions: scheduled → checked_in → completed (or cancelled).
* check_in() only from scheduled; check_out() only from checked_in with no existing calculated_fee.
* Illegal transitions raise ValidationError. Never bypass methods by setting timestamps directly in views. Correct late tap times only via update_actual_times().
* Do not pass skip_capacity=True except from VisitForm.save_all().

---
### 5. Business Rules Summary (do not change casually)

### Pipeline (per dog)

Inquiry → Meet & Greet → Evaluation → Approved 

### Dynamic Services & Pricing Model
*   **Decoupled Rates:** Financial pricing matrices, exact dollar figures, and hour boundaries are completely stripped from application source parameters. 
*   **Database Configurations:** Rates and rules are defined as transactional rows inside the `BusinessService` model layer, editable directly via management screens.
*   **Behavior Engine:** The checkout calculation framework evaluates pricing tiers dynamically based on relational behavioral rule triggers (`HOURLY` scaling, `OVERNIGHT` window crossings, or `CAPACITY_EXEMPT` drop-in visits).


### Customer vs dog (critical)

* **Customer** (CustomerOwner) = one per owner_email; owns COI
* **Dog** (ClientProfile) = owner_email + dog_name; owns pipeline, visits, vaccinations
* A customer may have **zero dogs** until David adds one
* Never invent a dog from the owner's first name on import
* **Standard stays (VisitForm create):** dog must be Approved, have current validated vaccination, and owner COI received — see customers.md / scheduling.md

### Visit status transitions (critical)

scheduled → checked_in → completed (or cancelled). 

* check_in() only from scheduled; check_out() only from checked_in with no existing calculated_fee
* Illegal transition calls raise ValidationError and must not overwrite actual_arrival, actual_departure, or calculated_fee
* After a late tap, update_actual_times() may correct arrival (checked-in) or arrival+departure (completed) and **does** recalculate fee when completed — intentional overwrite, not a second check-out

* check_out() refreshes from the DB first so a stale instance cannot re-price a finalized visit
* Views catch that error and redirect — no 500 on a mobile double-tap
* Do not set those fields (or status) in views to bypass the methods
* Capacity is enforced on booking saves, not on check-in/out/time-correction update_fields — a full day must not block checkout
* VisitForm.save_all() may pass skip_capacity=True after clean() already checked every occurrence; clone/admin/direct save() must not

------------------------------
## 6. Implementation Status

| Feature | Status |
|---|---|
| Customer/dog split UI | Done |
| New Client & Dog intake | Done — /clients/intake/, optional Meet & Greet visit |
| Vaccination expiry tracking | Done — dashboard 30-day / expired cards; /clients/?vax= |
| Structured owner address | Done — street / unit / city / province / postal; Maps + statements + vCard |
| Soft-hide dogs | Done — is_hidden; no UI hard-delete (visits/photos stay) |
| Pipeline per dog, COI per customer | Done |
| Visit booking (natural-language Start/End) | Done |
| Repeat series (daily/weekly/weekdays/monthly) | Done |
| Dashboard month calendar + daily agenda | Done |
| Mobile check-in/out + auto pricing | Done — status guards; correct late tap times via update_actual_times() |
| Booking confirmation email (Gmail OAuth) | Done |
| Google Contacts selective import + vCard | Done |
| iCal outbound /ical/ | Done |
| HTTPS dev server + ngrok | Done |
| Business settings (/settings/) | Done — identity, address, hours, phones, daily capacity |
| Booking iCal LOCATION + ORGANIZER from settings | Done — BusinessProfile → visit_email.py |
| Contemporaneous timeline (staff capture) | Done — photo/video, GPS, multi-dog, forward |
| Customer photo feed (secret link) | Done — /feed/<secret>/<dog>/, full history |
| Owner emergency + per-dog vet contacts | Done — see customers.md §2 |
| Feed access stats (visitor cookie) | Done — views + distinct browsers on dog detail |
| PWA install (David's phone) | Done — manifest, service worker, install banner |
| Business document uploads (COI, etc.) | Not started |
| Calendar inbound .ics import command | Partial — file-based, not live Gmail |
| Weekly statement email send | Partial — generates + formats; send not wired |
| Feed reactions, comments, public share (re-share, download) | Done — /feed/share/<token>/, dad4dogs_<uuid>.jpg — see feed.md |
| Feed push notifications | Planned |
| GoDaddy inquiry parsing | Not started |
| e-Transfer automation | Not started |
| Operational database PostgreSQL | Done — local Postgres 18; see platform.md |
| Schema multi-tenancy (Workspace + tenant FKs + CapacitySettings) | Done — Phase 1; single-operator bridge `get_active_workspace()` |
| Default tenant QuerySet / middleware | Not started — Phase 2 |
| Portable SQLite export (operator download) | Not started — future; billing.md section 8 |
| Multi-tenant auth / workspace membership | Not started — single-operator today |

------------------------------
## 7. Quick Commands

# Prerequisites: PostgreSQL running; copy .env.example → .env (POSTGRES_PASSWORD required)
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver_https 9000          # local HTTPS
python oauth_setup.py                          # first-time Gmail token
python manage.py gmail_auth --test you@email.com
python manage.py test operations

Set feed links in booking emails (ngrok or production):

$env:PUBLIC_SITE_URL = ""

------------------------------
## 8. LLM Session Checklist & Architectural Rules

### 8.1 LLM Session Checklist

   1. Identify the domain before editing (customers / scheduling / billing / admin / feed / platform). For structure or a large new domain, read `applicationphilosophy.md` first.
   2. Open the matching LLM/<domain>.md file. Treat `services.md` as next-build design only — do not implement until David asks.
   3. Keep mobile-first, one-handed UX. Standing rules in platform.md:
   * Lists (clients, statements, pending calendar, agenda, nested dogs/visits): minimize real estate. Flat rows, hairline dividers, name is the link, text-link actions. No per-item cards. Check-in stays a working surface with large CTAs.
      * Detail screens (customer, dog, future records) follow the labeled-card policy: each card named by job; Edit beside the name; .phone-row Calls; address visible; admin in More actions. Customer: Primary owner / Emergency & Pickups / Dogs. Dog: Dog / Veterinary / Visits.
      * Client list specifically: dense owner-first (Last, First), browser search, text Book. No Customer-only or Google Sync on that page.
   4. Visit booking stays two free-text fields (Start/End) — no multi-step pickers.
   5. No bulk Google contact import without preview + checkboxes.
   6. Extend operations/services/ for new business logic.
   7. Add tests in operations/tests.py for pricing, capacity, forms, or imports you touch. Capacity occupancy/blocks must follow Settings (capacity_limits()), not hardcoded 8/10.
   8. Do not bypass Visit.check_in() / check_out() status guards. Correct late tap times only via update_actual_times() (not by assigning timestamps in a view).
   9. Do not re-run full_clean() / capacity on check-in, check-out, or actual-time correction saves.
   10. Do not pass skip_capacity=True except from VisitForm.save_all().
   11. Never commit O-Auth Key/, certs/, or live client PII.

------------------------------
## 8.2 Architectural Guardrails & Coding Standards

   1. Package Domain Structure: Follow **`applicationphilosophy.md`**. Any file approaching ~150–200 lines must be split into a domain subdirectory package with an `__init__.py` re-export layer so external imports and urls.py routes remain uninterrupted. Reference: `views/scheduling/`, `views/customers/`, `views/feed/`.
   2. Explicit Template Context Wiring: Reusable action includes (e.g., moment_interactions.html) must receive all explicit endpoint variables (react_url, comment_url, asset_id, etc.) via {% include ... with ... %}. Never rely on implicit context inheritance for form actions.
   3. Database Architecture Strategy: Operational engine is PostgreSQL. Design for eventual multi-tenant isolation and optional compile-to-SQLite portability (`billing.md` section 8) — single-operator today; do not invent tenancy/export code unless asked.
   4. No In-Memory Table Aggregations: Views must not perform raw grouping loops across whole tables (e.g., defaultdict over entire querysets). Delegate filtering, grouping, and aggregations to custom QuerySet / Manager methods or service modules.

------------------------------
## 9. Domain Instruction Files

| File | Contents |
|---|---|
| customers.md | Owners, dogs, COI, vaccinations, contacts import |
| scheduling.md | Visits, repeat, dashboard, check-in/out status guards, pricing, capacity limits from Settings, calendar, booking email |
| billing.md | Weekly statements, checkout totals; portable SQLite export (future) |
| admin.md | Business settings, baseline contact info, daily capacity (standard + insurance max), documents |
| feed.md | Staff timeline, customer feed, speakable URLs, access logging |
| platform.md | Dev environment, HTTPS, ngrok, PWA, Gmail, cognitive-load UX, testing |
| applicationphilosophy.md | How we develop: small auditable files, domain packages, convention over configuration, anti-god-module — separate from product rules |
| services.md | **Next major build (design basis).** Configurable services/pricing catalog — not implemented. Live pricing still `scheduling.md` / `pricing.py`. Do not code until David starts that build. |
| Proposed work/ | Inbox of proposals — evaluate only; not standing spec. Empty of a topic means that idea is not on the table. See Proposed work/README.md. |
| Decisions/ | Archive of accepted, rejected, or partial proposals. History only. Live rules stay in the domain files named in each Decision header. |

------------------------------
## 9.1 SOC 2 Compliance Controls (Active Mapping Instructions)

### Multi-Tenant Access Boundaries (Confidentiality & Privacy Criteria) — **target / not fully implemented**

*Today the app is single-operator.* The bullets below are standing **design targets** for multi-tenant production. Do not invent workspace FKs unless David asks. Live feed visitor behavior is documented in `feed.md` (cookie `dad4dogs_feed_vid`).

* Active Isolation Enforcement: Data queries inside all operational views must enforce strict workspace boundaries tied to the authenticated operator's account context. Direct, global, un-scoped iterations across shared production tables are barred to secure tenant separation.
* Dynamic Export Compilation Strategy (**future**): Keep database layers structurally clean. Relational tables must map symmetrically so a tenant's isolated data rows can later be queried from production PostgreSQL and built into a standalone downloadable `.sqlite3` on demand (see `billing.md` section 8).

## Non-Repudiation, Verification, and Abuse Defense (Security Criterion)

* Visitor tracking (**live today**): Public feed interactions use a persistent cookie visitor id (`dad4dogs_feed_vid`). See `feed.md` for the real implementation.
* Visitor hash blend (**target / not implemented**): A future `visitor_hash` may SHA-256 blend IP + User-Agent + cookie for stronger non-repudiation. Do not treat that as current code.
* Anonymized Tracing Limits: Raw PII or raw visitor metadata must never bleed into system-level tracing logs or application console outputs.

------------------------------
## 10. Proposed work and Decisions 
LLM/Proposed work/ is a list of ideas we might put in the app. Read it only when David asks to evaluate a proposal. Do not code from it on a normal change.
When a proposal is decided (yes, no, or partial):

   1. Write any accepted rules into the matching domain file (platform.md, customers.md, …). That file becomes the live spec.
   2. Move the markdown into LLM/Decisions/, keeping the original filename (no accepted- / 1_ prefixes).
   3. Add a Decision header at the top: status, what we took, what we left, why, and where the live spec lives.
   4. Delete it from Proposed work so the inbox only holds open ideas.

*Notes*

   * **Partial work**  uses the same folder: the header says partial and lists what landed vs what did not. Rejected notes also go here with status rejected — one archive, not two.

   * Do not edit a Decisions file to change the product. Edit the domain file named in its header.



