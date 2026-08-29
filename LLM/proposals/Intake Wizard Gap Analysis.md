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


## Proposed changes and Python scratch code 

Here is the design and implementation specification for **Phase 1 (Service Catalog entries)** and **Phase 2 (Pipeline Gates & `IntakeWizardForm` linkage)**.

---

### 1. Catalog Definitions (`BusinessService`)

We define two dedicated system service records per workspace:

```python
# 1. Meet & Greet (Prerequisite interview)
name = "Meet & Greet"
target_category = "DOG"
base_rate = Decimal("0.00")
duration_type = "fixed"  # or 15 mins default
capacity_exempt = True   # Does not count against daily dog occupancy ceiling
is_active = True

# 2. Initial Evaluation (4-hour trial stay)
name = "Initial Evaluation"
target_category = "DOG"
base_rate = Decimal("15.00")
duration_type = "fixed"  # 4 hours
capacity_exempt = False  # Takes a real capacity spot in the pack
is_active = True

```

---

### 2. Multi-Tier Readiness Guards (`ClientProfile`)

Currently, `standard_stay_blockers()` only checks if a dog is ready for full `APPROVED` stays. We decompose this into explicit gate methods on `ClientProfile` in `operations/models/customers/dogs.py`:

```python
def evaluation_stay_blockers(self) -> list[str]:
    """Blockers for Step 3: Initial Evaluation (4 hours / $15)."""
    blockers = []
    if self.is_hidden:
        blockers.append(f"{self.dog_name} is hidden from the client list.")
    if self.pipeline_stage == self.PipelineStage.INQUIRY:
        blockers.append(f"{self.dog_name} must complete a Meet & Greet before an Initial Evaluation.")
    if not self.has_current_vaccination:
        blockers.append(f"{self.dog_name} has no current validated vaccination on file.")
    owner = self.customer_owner
    if not owner.coi_confirmed_received:
        blockers.append(f"Certificate of Insurance (COI) has not been confirmed for {owner.owner_name}.")
    return blockers

def standard_stay_blockers(self) -> list[str]:
    """Blockers for Step 4: Approved Regular Stays (Daycare / Boarding)."""
    blockers = self.evaluation_stay_blockers()
    if self.pipeline_stage != self.PipelineStage.APPROVED:
        blockers.append(
            f"{self.dog_name} is still in {self.get_pipeline_stage_display()}. "
            f"Standard stays require Approved status."
        )
    return blockers

```

---

### 3. Intake Wizard & Booking Form Integration

1. **`IntakeWizardForm` (`forms/intake.py`):**
* Automatically resolves and binds the `Meet & Greet` service (`$0.00`, `capacity_exempt=True`) when creating the introductory visit.


* Sets default duration to 15 minutes if only start time is provided.


* Sets `pipeline_stage = PipelineStage.MEET_GREET`.




2. **`VisitForm.clean()` (`forms/scheduling/visits.py`):**
* If `business_service` is **Meet & Greet**, bypass all paperwork and pipeline checks (`blockers = []`).


* If `business_service` is **Initial Evaluation**, evaluate `client.evaluation_stay_blockers()` (requires Vax + COI).


* For all other standard boarding/daycare services, evaluate `client.standard_stay_blockers()` (requires `APPROVED` + Vax + COI).





---

### 4. Implementation Steps

1. **Data Seed / Migration:** Add a migration or setup helper to ensure default `Meet & Greet` and `Initial Evaluation` services exist for workspaces.


2. **Model Method Updates:** Add `evaluation_stay_blockers()` to `operations/models/customers/dogs.py`.


3. **Form Logic Updates:** Update `IntakeWizardForm` to bind the M&G service, and update `VisitForm.clean()` to route checks based on the selected `business_service`.


4. **Run Verification:** `python manage.py test operations` to verify existing booking and intake tests remain green.



Ready to proceed with generating the code changes for `dogs.py` and `forms/scheduling/visits.py`?