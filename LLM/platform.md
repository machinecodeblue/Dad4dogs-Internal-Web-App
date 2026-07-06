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
- No public views except `/ical/` feed
- `SECRET_KEY` in settings — change before production deploy
- OAuth secrets and certs in `.gitignore`

---

## 7. Testing

```bash
python manage.py test operations
```

All tests in `operations/tests.py` (~55 tests). Update tests when changing:
- Pricing, capacity, visit forms, agenda, contacts, compliance, Gmail helpers, business settings

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