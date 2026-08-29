# Billing: Roadmap

Standing tracker (promoted from the former proposal). Services catalog gate is **lifted** for B1–B3.

## Sequencing

```
Billing view scaffolding     ← done
Docs + statements package    ← done (Phase 0)
B1 statement Gmail send      ← done
B2 unbilled summary          ← done
B3 service-aware line items  ← done
B4–B6                        ← deferred
```

## Slices

| ID | Slice | Status | Notes |
| --- | --- | --- | --- |
| **B1** | Wire `statement_send_email` | **Done** | Gmail plain send; `/statements/<id>/send/`; `sent` + `sent_at`; tests |
| **B2** | Unbilled summary | **Done** | `unbilled.py` + helper; list page hint when count > 0 |
| **B3** | Service-aware statements | **Done** | Snapshot `service_name` / `service_slug`; email + detail UI; no re-price |
| **B4** | Adhoc generate | Deferred | Product rules TBD |
| **B5** | Portable SQLite export | Deferred | PROJECT Rule C; single-operator today |
| **B6** | e-Transfer automation | Deferred | Needs stable send + payment rules |

## Ownership

| Concern | Home |
| --- | --- |
| HTTP | `views/billing/*` |
| Compile / format / send / unbilled | `services/statements/*` |
| Fees at checkout | `scheduling/pricing.md` |
| Catalog CRUD | `services.md` |
