# Decision

- **Status:** accepted
- **Live spec:** `LLM/platform.md` section 1 (Postgres tech stack + `.env`); `LLM/billing.md` sections 6 and 8 (portable SQLite export = future); `config/settings.py` / `requirements.txt` / `.env.example`
- **What we took:** Dev cutover to PostgreSQL 18 as the operational engine; fresh `migrate` schema; env-based `POSTGRES_*` credentials; no SQLite fallback; docs updated.
- **What we left:** SQLite data import from `db.sqlite3`; portable SQLite export pipeline/UI; multi-tenant workspace scoping.
- **Why:** Align the running app with `PROJECT.md` production-engine strategy without blocking on future portability/tenancy work.

---
# Plan: Postgres Migration (Dev Cutover)

## Context from `LLM/PROJECT.md`

The project strategy has shifted:

| Role | Technology | Purpose |
|------|------------|---------|
| **Production engine** | Community PostgreSQL | Multi-tenant isolation, concurrency, analytics, scale |
| **Portability artifact** | Standalone `.sqlite3` | Future on-demand export of one operator’s data context |

Standing rules (Rule C, §8.2.3, §9.1) say operational work runs on unified Postgres schemas, and SQLite remains a **compile-from-Postgres** portability path — not the live app database.

**This plan is intentionally narrow.** David chose option 1 with these constraints:

- Entire application must run on Postgres now.
- Apply the **existing Django model/migration structure** to a fresh Postgres database (`migrate`).
- **Do not** import or preserve data from the current `db.sqlite3`.
- SQLite customer-data extract / portable export is **future work** — note it, do not build it here.
- Multi-tenant workspace FKs / query scoping foundations are **out of scope** for this cutover (app remains single-operator for now).

Postgres **18.6** is already installed and verified locally (`postgresql-x64-18` Running on port `5432`, superuser `postgres`).

---

## Current state

| Area | Finding |
|------|---------|
| `config/settings.py` | Hardcoded SQLite: `ENGINE = django.db.backends.sqlite3`, `NAME = BASE_DIR / 'db.sqlite3'` |
| `requirements.txt` | No Postgres driver (`psycopg` / `psycopg2` absent) |
| Docs | `LLM/platform.md` and `README.md` still say SQLite; `PROJECT.md` already declares Postgres as the engine |
| Billing export | `PROJECT.md` mentions portable DB export triggers; `views/billing.py` is statements-only — no export code yet |
| Migrations | `operations/migrations/` through `0020_…` — ready to apply to empty Postgres |
| Secrets | `.env` already gitignored; settings already reads some `os.environ` values (Gmail, PUBLIC_SITE_URL) but does not load a `.env` file |
| Models | Standard Django fields + `JSONField` (statements / fee breakdown) — Postgres-compatible; no SQLite-only types |

---

## Goals

1. Django `default` database is Postgres for local development and tests.
2. Fresh empty schema created via existing migrations.
3. David can log in (new superuser) and run the app on port 9000 as today.
4. Docs (`platform.md`, `README.md`) match the new engine; `PROJECT.md` strategy stays authoritative.
5. Credentials stay out of git (env / `.env`).

## Non-goals

- Migrating rows from `db.sqlite3` (dumpdata/loaddata, custom ETL).
- Building the portable SQLite export pipeline or UI.
- Introducing tenant / workspace models or rewriting querysets for multi-tenant isolation.
- Production/Linode deployment hardening (beyond noting env-var patterns).
- Changing business rules, pricing, or visit guards.

---

## Implementation approach

### 1. Create the application database on local Postgres

Using `psql` as `postgres`:

- Create database: `dad4dogs` (UTF8).
- Prefer a dedicated login role `dad4dogs` with password stored only in local `.env` (not the superuser password in app config). Grant `CONNECT` + schema privileges on `dad4dogs`.
- Fallback if David prefers simplicity: use superuser `postgres` for local-only — document the security trade-off and still keep password in `.env`.

**Recommended:** dedicated role `dad4dogs` owning the `dad4dogs` database.

### 2. Add the Postgres driver

In `requirements.txt`:

```text
psycopg[binary]>=3.2
```

Django 5.2’s `django.db.backends.postgresql` uses psycopg 3. Install into the project venv with `pip install -r requirements.txt`.

Optional (recommended for Windows local DX): `python-dotenv` so a project-root `.env` is loaded in `settings.py` when present. `.env` is already gitignored.

### 3. Wire `DATABASES` from environment

Replace the SQLite block in `config/settings.py` with Postgres settings driven by env vars, for example:

| Variable | Default (local) |
|----------|-----------------|
| `POSTGRES_DB` | `dad4dogs` |
| `POSTGRES_USER` | `dad4dogs` |
| `POSTGRES_PASSWORD` | *(required — no insecure default in committed code)* |
| `POSTGRES_HOST` | `localhost` |
| `POSTGRES_PORT` | `5432` |

Engine: `django.db.backends.postgresql`.

Add `.env.example` (committed) with placeholder keys and no real secrets. Document in `platform.md` that David copies it to `.env` and fills the password.

Fail fast at startup if `POSTGRES_PASSWORD` is missing when not running a narrow management command that doesn’t need DB — or keep a clear `ImproperlyConfigured` message. Prefer explicit failure over silently falling back to SQLite (avoids “thought I was on Postgres” footguns).

### 4. Apply schema and bootstrap auth

```powershell
pip install -r requirements.txt
# ensure .env is set
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver_https 9000
```

No data import from SQLite. Media files under `media/` are filesystem-backed and remain usable without DB migration.

### 5. Verify

- `python manage.py check`
- `python manage.py test operations` against Postgres (Django will create/destroy `test_dad4dogs`; the DB user needs `CREATEDB` or use a superuser for tests only — grant `CREATEDB` to the app role for local, or document running tests as `postgres`).
- Smoke: login, dashboard, clients list, open settings (empty BusinessProfile created on first load as today).
- Confirm service `postgresql-x64-18` is Running.

### 6. Documentation updates (required for strategy alignment)

| File | Change |
|------|--------|
| `LLM/platform.md` | Tech stack: PostgreSQL 18 (local). Remove “Replace SQLite if concurrency demands it”. Add connection env vars, `.env` setup, migrate/createsuperuser notes. Note leftover `db.sqlite3` is obsolete local artifact. |
| `README.md` | Tech stack + Quick Start mention Postgres prerequisite and `.env`. |
| `LLM/billing.md` | One short “Future: portable SQLite export” note pointing at `PROJECT.md` § portability — so the cross-reference in PROJECT.md is honest without implementing export. |
| `LLM/PROJECT.md` | Only if a one-line Implementation Status / Quick Commands tweak is needed (e.g. “Operational DB: Postgres”). Avoid rewriting the strategy sections. |

### 7. Cleanup / hygiene

- Leave `db.sqlite3` on disk unless David wants it deleted; already gitignored. Optionally rename to `db.sqlite3.bak` locally after cutover so nobody accidentally opens the wrong file.
- Do not commit `.env`.
- Ensure `psql` / bin path remains on user PATH (already done during install).

---

## Future work (explicitly deferred)

Document in the plan/docs only — **do not implement now**:

1. **Portable SQLite export** — service that scopes an operator’s rows from Postgres and writes a downloadable `.sqlite3` (billing domain / `PROJECT.md` Rule C).
2. **Multi-tenant isolation** — workspace/tenant key on models + QuerySet managers so views never do global unscoped iteration (§9.1).
3. **SQLite → Postgres one-time data move** — only if David later decides he needs historical rows from the old file.

---

## Risk notes

| Risk | Mitigation |
|------|------------|
| Password / secrets in settings | Env + `.env` only; never commit real password |
| Tests need `CREATEDB` | Grant on local role or document test DB user |
| Docs still say SQLite → confusion | Update platform + README in same change set |
| Accidental dual-DB confusion | No SQLite fallback in settings |
| Empty DB after cutover | Expected; createsuperuser + re-enter business settings / clients as needed |

---

## Suggested implementation order (single change set)

1. Create Postgres DB + role.
2. Add `psycopg[binary]` (+ optional `python-dotenv`); `.env.example`.
3. Update `config/settings.py` `DATABASES`.
4. `migrate` + `createsuperuser`.
5. Run tests + quick manual smoke on HTTPS :9000.
6. Update `platform.md`, `README.md`, brief billing/future note.

---

## Success criteria

- [ ] App boots with `ENGINE = django.db.backends.postgresql` and no SQLite default.
- [ ] `migrate` applies `0001`–`0020` cleanly on empty `dad4dogs`.
- [ ] Superuser can sign in; dashboard loads.
- [ ] `python manage.py test operations` passes on Postgres.
- [ ] Docs describe Postgres as the operational database; SQLite mentioned only as future portability, not as the live engine.
