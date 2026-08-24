# Platform: Dev Environment, UI & Conventions

**Covers:** how to run the app, HTTPS/ngrok, Gmail OAuth, UI patterns, testing, and coding rules that span all domains.

---

## 1. Tech Stack

| Item | Value |
|------|-------|
| Framework | Django 5.x |
| Database | SQLite (`db.sqlite3`) |
| Timezone | `America/Toronto` |
| Auth | Django admin login; `@login_required` on all operational views |
| User model | Single user (David) — `createsuperuser` once, no registration |

### Dependencies (`requirements.txt`)
Django, icalendar, python-dateutil, werkzeug (HTTPS dev server), google-auth-oauthlib, google-api-python-client (Gmail send)

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
- Sticky header: "Dad4dogs / David's Internal Operations"
- Fixed bottom nav: **Home · Check-In · Clients · Billing · Settings**
- **Settings** (`/settings/`) — business baseline (see `admin.md`)
- Cards, large touch targets, green brand (`#2d6a4f`)
- Max content width ~600px centred

### Cognitive load (one-handed, dogs in hand)

**Standing rules** — accepted 2026-08-23 (original note in `Decisions/Gemini suggested UX cognitive overload guidelines.md`). New screens and template edits must follow these. Do not reintroduce wall-of-data cards. Change **this section** if the rules change; do not edit the Decisions archive.

**Progressive disclosure**
- **Customer & dog detail:** never more than 5 primary data points above the fold. Top card: full name, tap-to-call primary mobile, emergency (vet or contact) tap-to-call. Customer **Edit** is a small control beside the name and routes to the existing edit form — do not in-place-edit the summary. Customer **address, email, pickup** stay visible (they are short; extra clicks cost more than scroll). Dog clinic/feed/hide stay in `<details>` / **More actions**.
- **Customer COI:** proof, not a dashboard. Missing/awaiting = warning + actions on the profile card. Received = a **✓** beside the name only (tap to see date / clear). Do not give COI its own card.
- **Client list (`/clients/`):** compact rows `Dog Name · Owner Name · Status Badge · Primary Phone`. Do not nest full cards with notes, feed links, or address previews. Tap the row to open dog (or customer) detail. Group search/filter controls in a disclosure if more than 2 filters are present.

**Action density**
- At most **2 primary CTA buttons** visible at once per card (e.g. Call + Emergency, or Log Moment + Check Out).
- Dangerous or admin actions (Hide dog, regenerate feed, vCard, iCal) belong in a grouped **More actions** drawer. Customer **Edit** is beside the name. COI mark-sent / confirm-received sit on the profile card **only while outstanding**; once received, **✓** beside the name (tap to clear).

**Visual noise**
- At most **2 badges** per card. Only actionable states (expiring/missing vax, pipeline not Approved, CHECKED IN, COI not received on the *customer* screen). Do not show green OK badges for a normal state — no OK VAX, no COMPLETED, no capacity OK, no SENT.
- List notes and free text: one line with ellipsis (`.truncate`).

**Where this lands today**
- Dashboard agenda: compact rows; occupancy as `N / standard` from Settings (never a bare 0 for the ceiling); vax tiles only if count > 0; capacity **badge** only when warning/over; iCal in a disclosure.
- Check-in: Check In, or Log Moment + Check Out; emergency (else clinic) as tap-to-call, not a third button.
- Shared CSS in `base.html`: `.compact-row`, `.card-head`, `.truncate`, `details.disclosure`, `details.coi-mark`, `.admin-drawer`. Shared badges: `_pipeline_badge.html`, `_vax_badge.html` (warn/danger only).

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

All tests in `operations/tests.py`. Update tests when changing:
- Pricing, capacity (booking vs check-in/out saves), visit forms, check-in/out status guards, agenda, contacts, compliance, Gmail helpers, business settings, timeline, customer feed, PWA endpoints
- List/detail/dashboard/check-in templates — keep `CognitiveLoadUXTests` green (compact rows, no green OK badges, address in a disclosure, ≤2 primary CTAs)

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
- Replace SQLite if concurrency demands it
- Set `DEBUG=False`, proper `SECRET_KEY`, `ALLOWED_HOSTS`