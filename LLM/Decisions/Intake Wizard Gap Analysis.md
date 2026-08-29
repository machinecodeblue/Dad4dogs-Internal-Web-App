# Decision: Intake Wizard Gap Analysis

**Status:** accepted (complete for product scope)  
**Live spec:** `customers.md` (pipeline / dog profile), `scheduling/booking.md`, `scheduling/checkin.md`, `scheduling/pricing.md`, `services.md`  
**What we took:**
- Phase 1: `meet_greet` / `initial_evaluation` catalog; intake wired to M&G; capacity exempt; $0 / $15 via `pricing_engine`
- Phase 2: Pass/Decline + evaluation outcomes; `evaluation_stay_blockers` vs `standard_stay_blockers`; dog intake pipeline board; revert stage
- Follow-on: dedicated M&G / Evaluation schedule screens (not `VisitForm`)
**What we left / wontfix:** Agenda/dashboard M&G badges (original Phase 3.1) — **wontfix** unless a new proposal reopens them.  
**Why:** Prerequisite appointments needed catalog typing, gated progression, and a separate booking UI from recurring stays.

---

### 1. Architectural Gap Analysis


Currently, the intake pipeline and the scheduling models are loosely coupled through `ClientProfile.pipeline_stage`:

* `IntakeWizardForm` creates an owner, dog, and an optional visit, but that visit is just an untyped `Visit` record.


* Standard stay validation (`standard_stay_blockers()`) blocks non-`APPROVED` dogs from standard bookings, with an explicit exception: "Clone, calendar approve, and intake Meet & Greet bypass the form gate".


* **The Root Problem:** Because `Visit` records have no formal designation for their operational role (Prerequisite/M&G vs. Evaluation Stay vs. Standard Boarding), the scheduling system relies on form-level bypasses. An M&G shows up as a generic stay, can accidentally trigger capacity calculations or pricing logic meant for boarding, and does not automatically advance or enforce the 3-step intake workflow.



---

### 2. Concrete Domain Mapping for the 3-Step Lifecycle

To match your actual operations, the lifecycle maps to distinct model properties, service types, and pipeline gates:

| Stage | Duration & Fee | Operational Role | Validation / Gate Rules |
| --- | --- | --- | --- |
| **Step 1: Meet & Greet** | 15 mins, **$0** (Free) | Pre-intake interview & suitability check | Bypasses Vax & COI checks; capacity exempt (`capacity_exempt=True`); appears on calendar/agenda.

 |
| **Step 2: Paperwork Gate** | N/A (Admin) | Owner COI + Dog Vaccination validation | Required before moving to Step 3. Must confirm `coi_confirmed_received` and valid `VaccinationRecord`.

 |
| **Step 3: Initial Evaluation** | 4 hours, **$15** flat | Trial stay in the pack | Requires Step 1 completed + Step 2 paperwork validated. Subject to facility capacity.

 |
| **Step 4: Approved Client** | Standard catalog rates

 | Regular Daycare / Boarding | Standard booking rules apply.

 |

---

### 3. Execution Plan (Phased Delivery)

#### Phase 1: Service Catalog & Catalog Typing (Data Model)

1. **Catalog Definition:** Ensure the `BusinessService` table contains explicit entries for:
* `Meet & Greet` (Duration: 15m, Rate: $0.00, `capacity_exempt=True`, `target_category='DOG'`).


* `Initial Evaluation` (Duration: 4h, Rate: $15.00, `capacity_exempt=False`, `target_category='DOG'`).




2. **Linkage:** Tie the `IntakeWizardForm` and the M&G creation step explicitly to the `Meet & Greet` service rather than leaving `business_service` unassigned or pointing to regular boarding.



#### Phase 2: Pipeline State Machine & Validation Guards

1. **Pipeline Gate Enforcement:**
* Update `ClientProfile.standard_stay_blockers()` to clearly distinguish between **Evaluation Readiness** (requires M&G complete + Vax/COI valid) and **Standard Stay Readiness** (requires `pipeline_stage == APPROVED`).




2. **Stage Progression Automation:**
* When an M&G visit is checked out (or marked completed), provide an explicit UI prompt/action: "Pass Meet & Greet $\rightarrow$ Move to Paperwork / Evaluation".


* When an Evaluation stay is completed with positive review, provide a single-tap action to mark the client `APPROVED`.





#### Phase 3: Scheduling & Calendar Differentiation

1. **Agenda / Dashboard Rendering:**
* In `operations/views/scheduling/dashboard.py` and `components/scheduling/`, render Meet & Greet events with a distinctive badge (e.g., `M&G — 15m`) so it is instantly distinguishable from dogs checking in for full-day care or boarding.




2. **Pricing Engine Parity:**
* Ensure `_price_stay()` automatically recognizes the $0 M&G and $15 Evaluation services through `pricing_engine.py` without triggering legacy tier calculations.





#### Phase 4: Documentation Synchronization

1. Update `LLM/domains/customers.md` (Section 4: Pipeline Stages).


2. Update `LLM/domains/scheduling/booking.md` and `pricing.md` to reflect prerequisite service types and readiness gates.



---

Would you like to draft the proposed changes to the `IntakeWizardForm` and `standard_stay_blockers()` logic first, or review the catalog configuration for the Meet & Greet and Evaluation services?