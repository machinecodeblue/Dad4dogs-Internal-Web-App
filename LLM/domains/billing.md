# Domain: Billing

**Covers:** weekly statements, checkout fee totals on statements, statement email, future payment automation.

This domain is a **documentation package**. Deep rules live under [`billing/`](billing/) — do **not** load every topic file by default.

## Load order for billing work

1. This shim **or** [`billing/index.md`](billing/index.md)
2. **Only** the topic file for the task

| Task | File |
| --- | --- |
| Model / package map / status | [`billing/index.md`](billing/index.md) |
| Compile, list/detail UX | [`billing/statements.md`](billing/statements.md) |
| Format + Gmail send | [`billing/email.md`](billing/email.md) |
| Slice tracker B1–B6 | [`billing/roadmap.md`](billing/roadmap.md) |

**Also:** checkout fees → [`scheduling/pricing.md`](scheduling/pricing.md); catalog → [`services.md`](services.md).

**Code:** `operations/models/billing.py`, `operations/views/billing/`, `operations/services/statements/`
