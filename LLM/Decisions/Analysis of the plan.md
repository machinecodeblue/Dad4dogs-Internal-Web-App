# Decision: Analysis of the intake Phase 1 plan

**Status:** accepted — execution detail used for Phase 1 implementation  
**Live spec:** same as Decision *Intake Wizard Gap Analysis.md*  
**What we took:** Capacity-exempt probe invariant; $0 flat checkout via engine; 15m default; combined migration+form+tests pass; named tests.  
**What we left:** Field-name typo in draft (`start_at`/`end_at` → actual `meet_greet_*`).  
**Why:** Hardened Phase 1 without expanding into pipeline automation.

---

### 1. Invariant & Edge-Case Audit


* **Capacity Exemption Routing:**
Because `meet_greet` has `capacity_exempt=True`, passing `business_service=meet_greet` on the probe instance inside `IntakeWizardForm.clean()` guarantees that `check_visit_capacity()` takes the exemption branch and returns `status='ok'` without checking facility occupancy.


* **Same-Dog Overlap Preservation:**
Setting `business_service=meet_greet` will skip facility occupancy, but same-dog overlap validation in `overlapping_dog_visit()` still executes via `Visit.clean()` on create.


* **Checkout Pricing Invariant:**
Because `calculate_service_fee()` routes non-boarding or capacity-exempt DOG services to the flat `base_rate` branch, setting `base_rate=0.00` on `meet_greet` guarantees `$0.00` checkout totals without touching `operations/services/pricing_engine.py`.


* **15-Minute Default Duration Window:**
Calculating `end = start + timedelta(minutes=15)` server-side when `end_at` is empty provides a sensible default without blocking explicit custom durations if David enters a longer slot.



---

### 2. Implementation Execution Plan

#### Step 1: Data Migration (`0026_seed_intake_services.py`)

1. Create a data migration that iterates through existing `Workspace` rows (or active workspaces) and runs `get_or_create` on `BusinessService`:
* `slug='meet_greet'`: `name='Meet & Greet'`, `target_category='DOG'`, `base_rate=Decimal('0.00')`, `capacity_exempt=True`, `is_active=True`, `description='15-minute suitability visit'`.
* `slug='initial_evaluation'`: `name='Initial Evaluation'`, `target_category='DOG'`, `base_rate=Decimal('15.00')`, `capacity_exempt=False`, `is_active=True`, `description='~4h trial stay'`.


2. Optional backfill query: update legacy `Visit` records where `notes__icontains='Meet & Greet — intake'` to point `business_service` to the `meet_greet` service.

#### Step 2: Update `IntakeWizardForm` (`operations/forms/intake.py`)

1. **15-Minute Auto-Fill:** In `clean()`, if `start_at` parses successfully but `end_at` is empty/blank, default `scheduled_end = scheduled_start + timedelta(minutes=15)`.
2. **Service Resolution & Capacity Probe:**
* Fetch `BusinessService.objects.filter(tenant=workspace, slug='meet_greet', is_active=True).first()`.
* If missing, raise a form error (`"Meet & Greet service definition is missing"`).
* Construct the `Visit` probe with `business_service=meet_greet` so `check_visit_capacity(probe)` evaluates capacity exemption properly.




3. **Save Path:** Assign `business_service=meet_greet` and `notes='Meet & Greet — intake'` to the created visit instance before `visit.save()`.

#### Step 3: Test Suite Expansion (`operations/tests.py`)

Add unit and integration tests covering:

* `test_intake_wizard_assigns_meet_greet_service`: Validates `visit.business_service.slug == 'meet_greet'`.
* `test_intake_wizard_defaults_fifteen_minutes`: Validates duration when `end_at` is omitted.
* `test_intake_wizard_succeeds_when_facility_at_capacity`: Confirms `check_visit_capacity` does not block M&G on days where distinct dog counts exceed the insurance ceiling.


* `test_meet_greet_checkout_fee_is_zero`: Verifies `visit.check_out()` produces `$0.00` with flat line item breakdown.



#### Step 4: Documentation Sync

* Update `LLM/domains/customers.md` (Section 5 / Intake details).


* Update `LLM/domains/scheduling/booking.md` and `LLM/domains/scheduling/pricing.md`.


* Move `LLM/proposals/Intake Wizard Gap Analysis.md` to `LLM/decisions/` with completed status header.

Combining **I1 and I2** into a single implementation pass will deliver Phase 1 cleanly with zero dangling catalog states.