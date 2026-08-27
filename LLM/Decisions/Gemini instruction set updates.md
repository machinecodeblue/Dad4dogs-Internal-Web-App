# Decision

- **Status:** accepted (merged)
- **Live spec:** `LLM/platform.md` section 1 (Postgres tech stack + `.env` / settings); `LLM/billing.md` section 8 (multi-operator extraction deferred)
- **What we took:** Expanded platform Postgres/`.env`/zero-fallback/test-DB wording; billing future extraction architecture note; single-operator clarification.
- **What we left:** Gemini section number 14 (merged into platform section 1 instead of adding a duplicate section); "alphanumeric" password wording softened to secret credential.
- **Why:** Align instruction set with the completed Postgres cutover and keep portability explicitly future so LLMs do not invent export/tenancy code.

---

# platform.md


## 1. Tech Stack & Environment

| Item | Value |
|------|-------|
| Framework | Django 5.x |
| Database Engine | PostgreSQL 18.6 (Local Community Edition) |
| Port | 5432 |
| Driver Layer | `psycopg[binary]>=3.2` |
| Environment Loader | `python-dotenv` |
| Timezone | `America/Toronto` |
| Auth | Django admin login; `@login_required` on all operational views |
| User Model | Single administrative operator (David) |

## 14. PostgreSQL Local Development Environment Setup

### Environment Variables & Security Isolation
The application relies strictly on environment parameters for core database configurations. Real secrets must never be committed to source code or settings repositories. A project-root `.env` file (gitignored) must drive database operations.

*   `POSTGRES_DB`: Name of the active target database (`dad4dogs`).
*   `POSTGRES_USER`: The application-specific non-root login role (`dad4dogs`).
*   `POSTGRES_PASSWORD`: Secret alphanumeric security credential matching the database user.
*   `POSTGRES_HOST`: Default loopback routing address (`localhost` or `127.0.0.1`).
*   `POSTGRES_PORT`: Standard relational communication port (`5432`).

### Database Cutover Mechanics
*   **Zero Fallback Rule:** To prevent database confusion footguns, there is no silent fallback to SQLite in `config/settings.py`. If environment variables are missing or incorrect, the app raises an explicit `ImproperlyConfigured` exception at boot time.
*   **Legacy SQLite Status:** Leftover `db.sqlite3` files residing on local developer disks are deprecated artifacts. They may be safely renamed to `db.sqlite3.bak` or archived. Live features write exclusively to PostgreSQL.
*   **Test Database Management:** Running `python manage.py test operations` runs natively against a temporary test envelope created within PostgreSQL (`test_dad4dogs`). The local development database user requires `CREATEDB` permissions to handle automated setup and breakdown steps cleanly.

---

# billing.md

## 8. Multi-Operator Extraction Architecture (Future Deferral)

*   **Symmetric Relational Design:** Core models are constructed on a clean relational framework to ensure future portability compatibility. 
*   **Deferred Extraction Logic:** High-complexity operations—specifically the service pipeline that compiles one provider's specific database footprints out of PostgreSQL and into an portable download-ready `.sqlite3` binary container—are explicitly deferred. Feature design focuses on core operations until localized performance metrics are fully proven.
