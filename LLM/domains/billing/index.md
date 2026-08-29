# Domain: Billing (index)

**Covers:** weekly statements, fee snapshots, statement email, future payment automation.

**Do not load every file in this folder by default.** Start here — or the thin domain entry [`../billing.md`](../billing.md) — then open **only** the topic file for the task.

| Task | Load |
| --- | --- |
| Compile / list / detail | [`statements.md`](statements.md) |
| Email format + Gmail send | [`email.md`](email.md) |
| Slice tracker | [`roadmap.md`](roadmap.md) |
| This map | this file |

**Checkout pricing:** [`../scheduling/pricing.md`](../scheduling/pricing.md) — do not re-price in billing.  
**Catalog:** [`../services.md`](../services.md)

---

## Code packages

- `operations/models/billing.py` — `AccountStatement` (flat until a second model appears)
- `operations/views/billing/` — `list`, `detail`, `actions`, `helpers`
- `operations/services/statements/` — compile, format, send, unbilled, week bounds

Philosophy: [`../../PHILOSOPHY.md`](../../PHILOSOPHY.md) — keep views thin; orchestration in `services/statements/`.

```
operations/views/billing/
├── __init__.py      # statements_list, statement_detail, statement_send_email
├── list.py
├── detail.py
├── actions.py       # send (thin); adhoc later
└── helpers.py       # unbilled summary wrapper

operations/services/statements/
├── __init__.py      # Public re-exports
├── weeks.py
├── compile.py
├── format.py
├── send.py
└── unbilled.py
```

---

## Data model: `AccountStatement`

| Field | Purpose |
| --- | --- |
| `tenant` | Workspace (TenantAwareModel) |
| `client` | FK → `ClientProfile` (dog) |
| `week_start`, `week_end` | Statement period |
| `line_items` | JSON list of completed visits with fees (+ service identity when set) |
| `total_amount` | Sum due (CAD) |
| `send_status` | `draft` / `queued` / `sent` |
| `sent_at` | When emailed (nullable) |

Unique: one statement per dog per `week_start`.

---

## How fees get into statements

1. Checkout → `Visit.check_out()` / `_price_stay()` (see scheduling check-in + pricing docs)
2. `calculated_fee` + `fee_breakdown` on Visit
3. `generate_statements` → `generate_weekly_statements()` snapshots into `line_items`
4. Billing **never** recalculates overnight tiers — it reads Visit fees

---

## Implementation status

| Item | Status |
| --- | --- |
| Weekly compile | Done |
| List + detail + email preview | Done |
| Gmail statement send | Done (B1) |
| Unbilled summary | Done (B2) |
| Service-aware line items | Done (B3) |
| Adhoc generate | Deferred (B4) |
| Portable SQLite export | Deferred (B5) |
| e-Transfer automation | Deferred (B6) |

## Tenancy

Prefer `tenant=get_active_workspace()` on new billing queries when convenient. Single-operator bridge is enough until QuerySet Phase 2.

## Tests

Dedicated statement send / compile / unbilled tests in `operations/tests.py` as slices land. Pricing/checkout suites stay green.
