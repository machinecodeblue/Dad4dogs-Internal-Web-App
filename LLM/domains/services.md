# Domain: Services & Offerings

**Status:** Phase 2 **in progress / landing** — visits link to `BusinessService`; checkout uses `pricing_engine` when a service is set (DOG boarding parity with `pricing.py`); capacity skips for exempt / non-DOG.

**Covers:** Dynamic business services, customizable rates, categories, behavior rules; future capacity-exempt / pricing-engine cutover.

**Code packages:**
- `operations/models/services.py` — `BusinessService`, `ServiceBehaviorRule` (`TenantAwareModel`)
- `operations/forms/services.py` — `BusinessServiceForm`, `ServiceBehaviorRuleForm`
- `operations/views/services/` — catalog / edit / rules / actions / helpers
- `operations/services/pricing_engine.py` — used by `Visit._price_stay` when `business_service` is set (DOG boarding parity with `pricing.py`)

**Live pricing:** `scheduling/pricing.md` — legacy `operations/pricing.py` when service is null; catalog path via `pricing_engine` when linked (Short $15 / Daytime $25 / Overnight $37.50 for classic DOG boarding).

---

## 0. Package layout

```
operations/views/services/
├── __init__.py      # Re-exports public callables
├── catalog.py       # service_list
├── edit.py          # service_create, service_edit
├── rules.py         # rule_create, rule_delete
├── actions.py       # service_toggle_active, service_deactivate
└── helpers.py       # form_error_message
```

URLs under `/settings/services/`. Entry link on Business Settings tools card.

---

## 1. Purpose

Operators manage a commercial catalog without code changes — dog boarding, small-pet/property checks, etc. — via `/settings/services/`.

---

## 2. Data Model

### `BusinessService` (per workspace)

| Field | Purpose |
|-------|---------|
| `tenant` | FK → Workspace |
| `name` | Public name |
| `slug` | Unique per tenant (e.g. `overnight_stay`) |
| `summary` | Optional short customer-facing blurb for lists / future pickers (max ~240 chars) |
| `description` | **Required** full customer-facing **service plan** (plain text): what is included, expectations, boundaries |
| `staff_notes` | Optional **internal only** — never on customer emails, statements, or public pages |
| `target_category` | DOG / CAT / SMALL_PET / PROPERTY_ONLY |
| `rate_type` | FLAT / HOURLY / DAILY |
| `base_rate` | CAD |
| `is_active` | Soft-hide from future booking dropdowns |
| `capacity_exempt` | Column ready; **capacity.py not wired yet** (Phase 2) |

Unique: `(tenant, slug)`.

**Copy rules:** Customer-facing surfaces may use `summary` and `description` only. Behavior rules explain *pricing modifiers*, not the product story — the plan text is what makes the offering understandable in full.

### `ServiceBehaviorRule`

| Field | Purpose |
|-------|---------|
| `tenant` | FK → Workspace |
| `service` | FK → BusinessService |
| `trigger_type` | DURATION_UNDER / DURATION_OVER / TIME_WINDOW |
| `threshold_value` | Hours or window parameter |
| `modified_rate` | CAD when trigger matches |

Seeded defaults for Dad4dogs:
- Boarding: Short Visit $15, Daytime Visit $25, Overnight Stay $37.50 (DOG / FLAT, not capacity-exempt)
- Intake prerequisites: **Meet & Greet** (`meet_greet`, $0, `capacity_exempt=True`), **Initial Evaluation** (`initial_evaluation`, $15, not exempt) — migration `0026_seed_intake_services`

---

## 3. Phase boundaries

| Phase | Work |
|-------|------|
| **1 (done)** | Models, Settings CRUD, descriptions, seed, pricing_engine stub |
| **2a (done)** | `Visit.business_service` + required booking picker + plan summary/description on form |
| **2b (done)** | Checkout / fee correction uses `pricing_engine` when service set; DOG boarding ≡ `pricing.py` overnight-first |
| **2c (done)** | `capacity_exempt` or non-DOG skips facility capacity (overlap still enforced) |
| **3 (done)** | Billing service-aware statement lines (`scheduling` fees + `billing/statements` snapshot) |

---

## 4. Rules for LLMs

1. New bookings **require** an active `BusinessService`. Legacy visits may have `business_service=null` and still check out via `pricing.py`.  
2. Keep views thin; fee math for linked services goes through `services/pricing_engine.py` (DOG boarding reuses overnight-first helpers for parity).  
3. Scope queries with `get_active_workspace()` / `tenant=`.  
4. Soft-hide via `is_active`; do not hard-delete services with history (`on_delete=PROTECT` on visits).  
5. Always require a clear customer-facing `description` when creating/editing a service. Never leak `staff_notes` to customers.  
6. Capacity: skip facility caps when `capacity_exempt` or `target_category != DOG`; same-dog overlap always applies.

---

## 5. Tests

Add catalog CRUD tests when expanding Phase 1. Existing pricing/capacity suites must stay green (checkout unchanged).
