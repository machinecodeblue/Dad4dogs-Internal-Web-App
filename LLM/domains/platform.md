# Platform: Dev Environment, UI & Conventions

**Covers:** how to run the app, HTTPS/ngrok, Gmail OAuth, UI patterns, testing, and coding rules that span all domains.

---

## 1. Tech Stack & Environment

| Item | Value |
|------|-------|
| Framework | Django 5.x |
| Database engine | **PostgreSQL 18.6** (local community edition; Windows service `postgresql-x64-18`) |
| Database / role | `dad4dogs` / `dad4dogs` |
| Port | `5432` |
| Driver | `psycopg[binary]>=3.2` |
| Env loader | `python-dotenv` (project-root `.env`, gitignored) |
| Timezone | `America/Toronto` |
| Auth | Django admin login; `@login_required` on all operational views |
| User model | Single administrative operator (David) — `createsuperuser` once, no registration |

### Dependencies (`requirements.txt`)
Django, icalendar, python-dateutil, werkzeug (HTTPS dev server), google-auth-oauthlib, google-api-python-client (Gmail send), **psycopg[binary]**, **python-dotenv**

### PostgreSQL local setup (`.env` / `config/settings.py`)

The app relies on environment parameters for database config. Real secrets must never be committed. Copy `.env.example` → `.env` and set:

| Variable | Typical local value |
|----------|---------------------|
| `POSTGRES_DB` | `dad4dogs` |
| `POSTGRES_USER` | `dad4dogs` (app-specific non-root login role) |
| `POSTGRES_PASSWORD` | *(required — secret credential matching the DB user; no default in settings)* |
| `POSTGRES_HOST` | `localhost` (or `127.0.0.1`) |
| `POSTGRES_PORT` | `5432` |

**Zero fallback:** `config/settings.py` loads `.env` via `python-dotenv` and **requires** `POSTGRES_PASSWORD`. There is no silent SQLite fallback. Missing/incorrect env raises `ImproperlyConfigured` at boot.

**Legacy SQLite:** Leftover `db.sqlite3` on disk is a deprecated local artifact. Rename to `db.sqlite3.bak` or archive it. Live features write exclusively to PostgreSQL (`LLM/PROJECT.md` production engine).

**Tests:** `python manage.py test operations` creates a temporary `test_dad4dogs` database. The local `dad4dogs` role needs `CREATEDB`.

Fresh schema:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

**Operator scope today:** single-operator via `get_active_workspace()` (slug `dad4dogs`). **Schema** is multi-tenant (`Workspace`, `tenant` FKs, `CapacitySettings`) — see Decision *Multi-tenant schema Option B*. Default QuerySet tenant filters, membership auth, and portable SQLite export remain **future** (`PROJECT.md` Rule C / §9.1; `billing.md` §8).

---

## 2. Development Server

### Port
**9000** — David has another app on 8000.

### HTTP (basic)
```bash
python manage.py runserver 9000
```

### HTTPS (recommended — matches production feel)
```bash
python manage.py runserver_https 9000
```
Uses mkcert certs in `certs/`. Setup: `scripts/setup-certs.ps1`

### ngrok (mobile access)
```bash
ngrok http https://127.0.0.1:9000
```
Or: `scripts/run-dev-tunnel.ps1`

`ALLOWED_HOSTS` includes `.ngrok-free.app`, `.ngrok-free.dev`, `.ngrok.io`  
`NgrokCsrfMiddleware` trusts ngrok origins in dev.

---

## 3. Gmail OAuth (booking emails)

Credentials live in `O-Auth Key/` (gitignored):
- `client_secret_*.json` — Google Desktop OAuth client
- `token.json` — created by one-time browser sign-in

```bash
python oauth_setup.py                              # first time
python manage.py gmail_auth                      # check status
python manage.py gmail_auth --test you@email.com   # verify send
```

Implementation: `gmail_paths.py`, `gmail_send.py`, `visit_email.py`  
Messages appear in Gmail **Sent Mail** for audit trail.

---

## 4. UI Conventions

### Layout
- Sticky **top** header (Android Chrome–first; no fixed bottom app nav — browser chrome already owns the bottom):
  - **Dad4dogs** logo → Home (`/`)
  - Primary links: **Check-In** · **Clients**
  - **☰** drawer: **Billing** · **Settings** · **Calendar pending** · **Contacts**
- PWA install remains optional; navigation must work in a normal browser tab without standalone mode
- **Settings** (`/settings/`) — business baseline (see `admin.md`); reached from the drawer, not a primary tab
- Cards, large touch targets, green brand (`#2d6a4f`)
- Max content width ~600px centred

### Lists vs details

Two different jobs:

| Screen type | Job | Density |
|-------------|-----|---------|
| **List** (`/clients/`, `/statements/`, `/calendar/pending/`, dashboard agenda, nested dogs/visits) | Scan, pick, go | **Minimize real estate** — flat rows, hairline dividers, no per-item cards |
| **Detail** (customer, dog, future records) | Understand one record | Labeled cards (below) |
| **Working surface** (`/checkin/`, visit timeline) | Do the day’s work | Large Check In / Log Moment / Check Out stay; do not flatten those CTAs |

### Lists (minimize real estate) — standing policy

A listing of items is a **juncture**. The core tenet is **use as little vertical space as possible** so 25–50 rows stay scannable.

- One toolbar (search/filters/primary add) + **one** list. Hairline dividers (`.client-row` / `.compact-row`). **Do not wrap each item in its own padded `.card`.**
- The **name is the link** to the record. Do not add a full-width View button per row.
- Row actions are **text links** or `btn-sm` (Book, Approve). Never a full-width button on every row.
- Search, when the set is ~50 or fewer, runs **in the browser** on the loaded list.
- Sort for people lists: `Last, First`.
- Admin tools (Google Contact Sync, iCal) do not live on a list screen.

`/clients/` is the reference implementation. Copy that density, not the old per-client cards.

### Detail screens (labeled cards) — standing policy

This is the expected look for **every record-detail screen** (customer, dog, and any future detail). Forms (intake, edit customer, edit dog, visit) stay as they are. Change **this section** if the pattern changes.

Each card has one job. A kicker (`.card-kicker`) or `h2` names that job so the purpose is obvious before you read the body. Do not ship an untitled stack of buttons.

| Rule | How it looks |
|------|----------------|
| **Label** | `.card-kicker` or `h2` — Primary owner contact, Emergency & Pickups, Dog, Veterinary, Visits, Dogs |
| **Identity** | Name + **Edit** (small, beside the name) opens the **existing edit form**. Not in-place editing. At most two actionable badges. |
| **Phones** | Number and compact **Call** in `.phone-row`, next to the person or clinic they belong to. Owner Call is green `btn-primary btn-sm`. Emergency (person or vet) is yellow `btn-warn btn-sm`. No full-width Call stacked under the title. |
| **Proximity** | Name + role + number + Call are one unit (e.g. “David — Emergency contact” then yellow Call). |
| **Visible facts** | Short always-needed text stays visible (owner address on customer; drop-off address on dog). Extra clicks cost more than a little scroll. |
| **Lists** | Compact rows. One header action (Add dog, Schedule stay). |
| **Admin** | Feed, hide, vCard, regenerate, pipeline — **More actions**. Not a third primary button. |

**Customer (`/customers/<id>/`)**
- **Primary owner contact** — name, Edit, phone + Call, email, address/maps. COI missing = warning + mark sent/received. COI received = **✓** beside the name (tap to clear). No dedicated COI card.
- **Emergency & Pickups** — own card. Emergency person labeled; yellow Call on *their* number. Authorized pickup listed and labeled.
- **Dogs** — compact rows + Add dog.

**Dog (`/dogs/<id>/`)**
- **Dog** — name, Edit, pipeline/vax badges, **Vaccinations** (always a link to `/dogs/<id>/vaccinations/` — papers are not on the Edit form). Owner + Call, drop-off address if on file.
- **Veterinary** — own card when vet data exists. Emergency vet is one unit (name + yellow Call). Clinic phone is a compact Call, not a second full-width button under the dog’s name.
- **Visits** — compact rows + Schedule stay.
- Photo feed and hide/vCard stay in disclosures / More actions.

**Do not add SMS** unless David asks. Do not put a second Edit on every card — one Edit on the identity card is enough.

**Client list (`/clients/`) — dense, owner-first**
- A listing screen is a **juncture**, not a stack of padded cards. One toolbar + one flat list with hairline dividers. ~25–50 clients: load the (filtered) list and **search in the browser** (owner name + dog name). Do not round-trip the server on every keystroke.
- Toolbar: search, **+ New Client** (intake only — a client without a dog is not a Clients-list action). Stage and vax `<select>`s inline. **No More accordion. No Customer only. No Google Contact Sync here** — sync is on Settings.
- Rows: `Last, First — phone` (name is the profile link). Dogs nest under the owner. **Book** is a small text link only when the dog is bookable (Approved + current vax + COI). If not, show **Needs approval** / **Needs vax** / **Needs COI** instead — never a Book that will bounce on the form. Missing papers use the **NO VAX** badge, not `VAX`.
- Do not restore per-client white cards or full-width View/Book buttons on this page.

**Action density**
- At most **2 primary CTA buttons** visible at once per card (check-in: Log Moment + Check Out). Detail phones use compact `.phone-row` Calls instead of two full-width stacked buttons.
- Dangerous or admin actions belong in **More actions**.

**Visual noise**
- At most **2 badges** per card. Only actionable states (expiring/missing vax, pipeline not Approved, CHECKED IN, COI not received on the *customer* screen). Do not show green OK badges for a normal state — no OK VAX, no COMPLETED, no capacity OK, no SENT.
- List notes and free text: one line with ellipsis (`.truncate`).

**Where this lands today**
- Dashboard agenda: compact rows; occupancy as `N / standard` from Settings (never a bare 0 for the ceiling); vax tiles only if count > 0; capacity **badge** only when warning/over; iCal in a disclosure.
- Check-in: Check In, or Log Moment + Check Out; emergency (else clinic) as tap-to-call, not a third button.
- Shared CSS in `base.html`: `.app-header` / `.app-primary-nav` / `.nav-drawer` (top nav), `.client-row` / `.compact-row` (dense lists), `.list-toolbar`, `.card-head`, `.card-kicker`, `.phone-row`, `.truncate`, `details.disclosure`, `details.coi-mark`, `.admin-drawer`. Shared badges: `_pipeline_badge.html`, `_vax_badge.html` (warn/danger only).

### Template packages (`includes/` vs `components/`)

Same packaging idea as Python: prefer small templates with one job. Screen shells stay thin; reusable product UI lives in named partials.

| Location | Use for |
|----------|---------|
| `operations/templates/operations/includes/` | App chrome and feed social already wired: nav, messages, PWA modals, `moment_interactions`, share sheets |
| `operations/templates/operations/components/<domain>/` | **New** product UI partials (scheduling forms, staff timeline capture/cards). Prefer this over new root `_*.html` files |
| Root `_pipeline_badge.html`, `_vax_badge.html`, `_address_fields.html` | Legacy shared badges/fields — keep working; do not add more root partials |

**Rules for LLMs**

1. Explicit context: `{% include "operations/components/…" with … only %}` — no magic inheritance for action endpoints (`PHILOSOPHY.md`).
2. Split when a screen approaches ~150–200 lines or ~10 KB (e.g. former `visit_timeline` / `visit_form` monoliths).
3. Partials first; move CSS/JS to `static/operations/` only when **two or more** screens share it.
4. Do not redesign UX while extracting — preserve IDs/classes the page scripts rely on.

**Staff timeline:** `components/timeline/` (`capture_form`, `moment_card`, `forward_panel`, styles/script includes).  
**Visit booking form:** `components/scheduling/` (datetime, repeat, service plans, email confirm, clone).

### Progressive Web App (PWA) — David's admin app only
Install to home screen for standalone mode (no browser address bar). Customer feed is a normal web page — they can bookmark or add to home screen manually.

| URL | Purpose |
|-----|---------|
| `/manifest.webmanifest` | Web app manifest (`display: standalone`; absolute icon/start URLs) |
| `/sw.js` | Service worker (`dad4dogs-v2`; network-only; enables install) |

Icons: `operations/static/operations/pwa/`  
Implementation: `operations/views/pwa.py`  
Session: 30-day cookie (`SESSION_COOKIE_AGE`) so David stays signed in on his phone.

**Install banner** (`base.html` + `install.js`):
| Platform | Behaviour |
|----------|-----------|
| **iOS Safari** | Banner immediately → **INSTALL** opens Share → Add to Home Screen guide |
| **Android Chrome** | `beforeinstallprompt` when available; **2s fallback** banner if not |
| **Desktop Chrome** | `beforeinstallprompt` or 2s fallback |
| **Android manual** | INSTALL without native prompt → Chrome ⋮ menu overlay |

**Dismiss:** × stores `dad4dogs-pwa-install-dismissed` in `localStorage`  
**Installed:** `appinstalled` or standalone mode hides banner permanently  

Requires **HTTPS** (`runserver_https` + ngrok). ngrok interstitial on first visit can delay PWA detection on mobile.

### Public URLs (no login)
| Path | Purpose |
|------|---------|
| `/ical/` | David's read-only calendar feed |
| `/feed/<secret>/<dog-slug>/` | Customer photo feed — react, comment, share — see `feed.md` |
| `/feed/share/<token>/` | Single-moment public share — react, comment, re-share, download (`dad4dogs_<uuid>.jpg`) |
| `/feed/share/<token>/download/` | Attachment download for shared moment |

Set `PUBLIC_SITE_URL` env var so booking emails and copied feed links use the full tunnel/production URL.

### Badge colours
| Class | Meaning |
|-------|---------|
| `badge-ok` (green) | Normal / approved / email sent |
| `badge-warn` (yellow) | Warning, capacity, duplicates |
| `badge-danger` (red) | Blocked, validation issue |

Templates: `operations/templates/operations/`  
Base template: `base.html` (messages, nav, form input styles)

---

## 5. File Organization Rules

1. **Domain packages** for models, forms, views — see `PROJECT.md` §3
2. **Business logic** → `operations/services/` (not views)
3. **Never create monolithic files** — split when approaching ~200 lines
4. **`__init__.py` glue** — external imports stay stable (`from operations.models import Visit`)
5. **Migrations** — schema changes only; domain splits do not need migrations

### Purge stale bytecode after refactors
```powershell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
```

---

### Template Architecture & Anti-Monolith Rules

To prevent template bloat, avoid "God scripts," and ensure browser-level CSS caching, adhere to the following decomposition standards:

- **No Massive Inline Styles or Scripts:** Never embed large CSS blocks or multi-function JavaScript listeners directly inside root layout templates (`base.html`, `customer_base.html`).
  - Component and layout styles belong in static stylesheets (`operations/static/operations/css/app.css`).
  - PWA-specific install and platform overlay styles belong in `pwa-install.css` (or partitioned inside `app.css`).
  - Isolated DOM behaviors (e.g., slide-out navigation drawers, modals) belong in standalone JS files (`operations/static/operations/js/`).

- **Modular Template Partials (`includes/`):** Break shared or repetitive HTML structures out of parent templates into partial includes prefixed with an underscore or descriptive name:
  - `_header_nav.html` — App-wide sticky header, brand link, and drawer menu.
  - `_messages.html` — Django flash alert message rendering.
  - `_pwa_install_modals.html` — Android fallback guide and iOS Safari "Add to Home Screen" overlay DOM.
  - `includes/moment_interactions.html`, `includes/share_sheet.html`, etc. — Shared social reaction bars, share sheets, and interactive scripts shared between private customer feeds and public share pages.

- **Root Template Footprint:** `base.html` must serve strictly as a structural skeleton (~45–60 lines max), orchestrating block definitions (`{% block content %}`, `{% block extra_head %}`), meta tags, static asset links, and modular includes.


---

## 6. Authentication & Security

- `LOGIN_URL` = `/admin/login/`
- `@login_required` on all staff views (dashboard, clients, timeline capture, settings, etc.)
- **Public views:** `/ical/`, `/feed/<secret>/<dog-slug>/`, `/feed/share/<token>/` (+ react/comment/download), `/manifest.webmanifest`, `/sw.js`
- Customer feed uses **secret link** auth — no passwords; regenerate revokes old links
- `SECRET_KEY` in settings — change before production deploy
- OAuth secrets and certs in `.gitignore`

---

## 7. Testing

```bash
python manage.py test operations
```

Tests live in the `operations/tests/` package (not a single monolith):

| Package | Coverage |
| --- | --- |
| `operations/tests/customers/` | Forms, views/UX, intake/pipeline, contacts, compliance/vax |
| `operations/tests/scheduling/` | Visits/repeats, check-in, capacity, agenda, pricing, calendar/email |
| `operations/tests/feed/` | Timeline, feed interactions, PWA / geolocation / business settings / statement smoke |

Update the matching module when changing pricing, capacity (booking vs check-in/out saves), visit forms, status guards, agenda, contacts, compliance, Gmail helpers, business settings, timeline, customer feed, or PWA endpoints. Keep `CognitiveLoadUXTests` green (compact rows, no green OK badges, address in a disclosure, ≤2 primary CTAs).

---

## 8. Management Commands

| Command | Purpose |
|---------|---------|
| `runserver_https` | HTTPS dev server |
| `gmail_auth` | OAuth status / test send |
| `generate_statements` | Weekly billing compile |
| `import_calendar` | Inbound `.ics` file |

---

## 9. Data Samples

`Data samples/google_contacts.csv` — real Google export format for parser tests.  
Do not commit new live client PII without David's consent.

---

## 10. Deployment Notes (future)

- Target: 2GB Linode instance
- Move `O-Auth Key/token.json` to secure path via `GMAIL_OAUTH_DIR` env var
- Keep PostgreSQL as the operational database; supply `POSTGRES_*` via host env (not committed `.env`)
- Set `DEBUG=False`, proper `SECRET_KEY`, `ALLOWED_HOSTS`