# Proposed: Billing package roadmap

**Status:** Open — scaffolding landed; feature slices wait on **services**  
**Live spec today:** `LLM/billing.md`  
**Depends on:** `LLM/services.md` (next major build); multi-tenant schema Phase 1 (done)  
**Philosophy:** `applicationphilosophy.md` — keep `views/billing/` thin; orchestration in `services/`

---

## 1. Goal

Finish the billing **domain package** in ordered slices **after** the services/pricing catalog exists. Do not deepen statement product behavior on hardcoded `pricing.py` tiers alone — that work would be re-done once `BusinessService` / behavior rules ship.

---

## 2. Current state (scaffolding)

```
operations/views/billing/
├── __init__.py
├── list.py              # LIVE — statements_list
├── detail.py            # LIVE — statement_detail + email preview
├── actions.py           # STUB — statement_send_email (placeholder; no URL yet)
└── helpers.py           # STUB — get_unbilled_summary_for_client (pass)
```

| Already done | Not done |
|--------------|----------|
| Weekly compile (`generate_statements`) | Gmail statement send |
| List + detail UI | Unbilled summary UX |
| View package split | Service-aware line items |
| `AccountStatement.tenant` | Adhoc generate, portable SQLite export, e-Transfer |

---

## 3. Non-goals until services Phase 1

- Redesigning statement line-item schema around services  
- Portable SQLite export UI  
- e-Transfer automation  
- Treating `statement_send_email` stub as production  

**Allowed anytime:** doc alignment, URL/name hygiene, tiny stub fixes that do not invent product rules.

---

## 4. Sequencing

```
Billing view scaffolding     ← done
Docs + this roadmap          ← done when accepted into standing docs/Decision flow
Services domain build        ← NEXT (catalog, rates, capacity_exempt, …)
Billing feature slices B1–B6 ← after services
```

---

## 5. Post-services slices (ordered)

| ID | Slice | Notes |
|----|--------|------|
| **B1** | Wire `statement_send_email` | Gmail OAuth like booking email; URL + `operations:statement_detail` redirect; set `send_status=sent`, `sent_at`; tests |
| **B2** | Unbilled summary | Implement `helpers.get_unbilled_summary_for_client`; optional list/detail surfacing |
| **B3** | Service-aware statements | Line items / fees reflect `BusinessService` (+ behavior rules); keep pricing engine ownership clear vs scheduling |
| **B4** | Adhoc generate | `generate_adhoc` (or similar) in `actions.py`; thin view, logic in `services/statements.py` |
| **B5** | Portable SQLite export | Tenant-scoped compile from Postgres; action under billing; see `billing.md` §8 / PROJECT Rule C |
| **B6** | e-Transfer automation | Last — depends on stable statement + payment product rules |

---

## 6. Tenancy

Phase 1 schema already puts `tenant` on `AccountStatement`. Until QuerySet Phase 2, single-operator bridge is enough. New billing queries should prefer explicit `tenant=get_active_workspace()` when convenient so Phase 2 is easier.

---

## 7. File ownership

| Concern | Home |
|---------|------|
| HTTP list/detail/actions | `views/billing/*` |
| Compile / format / send orchestration | `services/statements.py` (+ future `billing_export.py`) |
| Fee calculation at checkout | `scheduling` / `pricing.py` (evolves with services) |
| Settings / capacity | `admin.md` / `CapacitySettings` — not billing |

Do not grow `actions.py` into a god module — split further if it approaches ~150–200 lines.

---

## 8. Acceptance when this proposal is “done”

- Standing docs (`billing.md`, PROJECT tree) match package layout  
- This roadmap lives in Proposed work until services ship; then either Decision-archive or tick slices as they land  
- No billing product slice started before services Phase 1 without David explicitly overriding  
