# Domain: Billing

**Covers:** weekly statements, checkout fee totals, future payment automation.

**Code packages:** `operations/models/billing.py`, `views/billing.py`  
**Services:** `operations/services/statements.py`  
**Related:** checkout pricing lives in `scheduling` domain (`pricing.py`, `Visit.check_out()`)

---

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

1. David checks out a visit → `Visit.check_out()` runs pricing engine
2. `calculated_fee` and `fee_breakdown` saved on `Visit`
3. `generate_statements` management command compiles completed visits per dog per week
4. Statement `line_items` snapshot visit dates, fees, and breakdown JSON

**Pricing rules** are defined in `scheduling.md` / `PROJECT.md` — do not duplicate tier logic here.

---

## 3. Screens & URLs

| Path | Purpose |
|------|---------|
| `/statements/` | List all statements |
| `/statements/<id>/` | Detail + formatted email body preview |

Bottom nav **Billing** links here.

---

## 4. Statement Generation

```bash
python manage.py generate_statements
```

- `statements.py` — `generate_weekly_statements()`, `format_statement_email()`
- Groups by dog (`client_id`) for the week
- Sets `send_status = queued` on create/update
- Email body includes visit lines + total + e-Transfer reminder text

---

## 5. Views (billing.py)

`statements_list`, `statement_detail`

---

## 6. Implementation Status

| Item | Status |
|------|--------|
| Compile weekly statements | Done |
| Format email body (preview on detail page) | Done |
| Send statement via Gmail | **Not wired** — use booking email pattern when implementing |
| e-Transfer send automation | Not started |
| Zero-admin accounting dashboard | Partial — list + preview only |

---

## 7. When Adding Statement Email Send

Reuse the Gmail OAuth stack from scheduling:
- `operations/services/gmail_send.py`
- `O-Auth Key/token.json`
- `python manage.py gmail_auth --test`

Mark `send_status = sent` and `sent_at` after successful send.

---

## 8. Tests

Statement logic is covered indirectly via pricing/checkout tests. Add dedicated statement tests when email send is wired.