# Domain: Billing

**Covers:** weekly statements, checkout fee totals, future payment automation.

**Code packages:** `operations/models/billing.py`, `views/billing/`  
**Services:** `operations/services/statements.py`  
**Related:** checkout pricing lives in `scheduling` domain (`pricing.py`, `Visit.check_out()`)

---
## 0. Package layout

Scaffolding follows `applicationphilosophy.md` (same pattern as `scheduling/`, `customers/`, `feed/`). Not a finished product — stubs are intentional until **services** lands.

```
operations/views/billing/
├── __init__.py          # Stable public re-exports (statements_list, statement_detail, statement_send_email)
├── list.py              # statements_list (dense scannable listing) — live
├── detail.py            # statement_detail (statement view & email preview) — live
├── actions.py           # statement_send_email stub; generate_adhoc later
└── helpers.py           # get_unbilled_summary_for_client (stub)
```

## 1. Data Model

### `AccountStatement`
| Field | Purpose |
|-------|---------|
| `client` | FK → `ClientProfile` (dog) |
| `week_start`, `week_end` | Statement period |
| `line_items` | JSON list of completed visits with fees |
| `total_amount` | Sum due (CAD) |
| `send_status` | `draft` / `queued` / `sent` |
| `sent_at` | When emailed (nullable) |

Unique constraint: one statement per dog per `week_start`.

---

## 2. How Fees Get Into Statements

1. David checks out a visit → `Visit.check_out()` runs pricing engine (only from `checked_in`; see `scheduling.md` §5)
2. `calculated_fee` and `fee_breakdown` saved on `Visit`
3. `generate_statements` management command compiles completed visits per dog per week
4. Statement `line_items` snapshot visit dates, fees, and breakdown JSON

**Pricing rules** are defined in `scheduling.md` / `PROJECT.md` — do not duplicate tier logic here.

---

## 3. Screens & URLs

| Path | Purpose |
|------|---------|
| `/statements/` | Dense list (same tenet as `/clients/`): one card, hairline rows, name is the link. Amber badge only when not yet sent. |
| `/statements/<id>/` | Detail + formatted email body preview |

Drawer **Billing** links here (not a bottom-nav tab — see `platform.md` §4).

---

## 4. Statement Generation

```bash
python manage.py generate_statements
```

- `statements.py` — `generate_weekly_statements()`, `format_statement_email()`
- Groups by dog (`client_id`) for the week
- Sets `send_status = queued` on create/update
- Email body includes visit lines + total + e-Transfer reminder text
- Includes owner `Address:` (one-line structured address) when on file — from `CustomerOwner`, not the dog row

---

## 5. Views (`views/billing/`)

| Callable | Module | Status |
|----------|--------|--------|
| `statements_list` | `list.py` | **Live** — dense statement list |
| `statement_detail` | `detail.py` | **Live** — detail + email preview |
| `statement_send_email` | `actions.py` | **Stub** — placeholder message; no URL wired yet |
| `get_unbilled_summary_for_client` | `helpers.py` | **Stub** — `pass` |

Re-exported via `views/billing/__init__.py` → `views/__init__.py` for `urls.py`. No portable-database export endpoints yet (future → `actions.py` or dedicated service).

---

## 6. Implementation Status

| Item | Status |
|------|--------|
| Compile weekly statements | Done |
| Format email body (preview on detail page) | Done |
| Send statement via Gmail | **Not wired** — use booking email pattern when implementing |
| e-Transfer send automation | Not started |
| Zero-admin accounting dashboard | Partial — list + preview only |
| View package split (`views/billing/`) | **Done** — scaffolding; see §0 |
| Portable SQLite export (operator data download) | **Future** — compile from Postgres; see `PROJECT.md` Rule C / §9.1. Not started. |
| Full billing cycle (service-aware lines, adhoc, e-Transfer) | **Blocked on services domain** — see `Proposed work/Billing package roadmap.md` |

---

## 7. When Adding Statement Email Send

Reuse the Gmail OAuth stack from scheduling:
- `operations/services/gmail_send.py`
- `O-Auth Key/token.json`
- `python manage.py gmail_auth --test`

Mark `send_status = sent` and `sent_at` after successful send.

---

## 8. Multi-Operator Extraction Architecture (Future Deferral)

The app is **single-operator today**. Do not implement extraction or invent tenancy from this section unless David asks.

* **Symmetric relational design:** Keep core models on a clean relational schema so a future portability pipeline can map tables without special-case blobs.
* **Deferred extraction logic:** Compiling one operator's footprint out of production PostgreSQL into a downloadable standalone `.sqlite3` is **explicitly deferred**. No UI, management command, or `views/billing/actions.py` export trigger exists yet. Focus on statement scaffolding and **services** before expanding the billing cycle (`PROJECT.md` Rule C / section 9.1; Proposed work *Billing package roadmap*).

---

## 9. Tests

Statement logic is covered indirectly via pricing/checkout tests. Add dedicated statement tests when email send is wired.