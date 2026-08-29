# Decision: Review of Intake Work

**Status:** accepted — dog profile intake board + paperwork card + appointment badges + revert stage landed  
**Live spec:** `customers.md` (dog screen / pipeline), `scheduling/booking.md`, `scheduling/checkin.md`  
**What we took:** Guided Intake pipeline card with one primary CTA; Vaccination & COI card; Appointments list with MEET & GREET / EVALUATION / STAY badges; Revert to previous stage; keep Pass/Decline outcome gate.  
**What we left:** Agenda calendar badges.  
**Why:** Prior UX was fragmented; Lulu’s screen did not show an obvious Schedule Meet & Greet path.

---

### Critical Issues Identified in the Screenshots

1. **Missing Intake Appointment:** In your third screenshot (Dog Screen for Lulu), the **Visits** card displays `"No visits yet."` If a Meet & Greet was scheduled during intake or afterwards, it was either dropped by the form save or not linked to the dog profile.
2. **Invisible Pipeline Status & Progression:** The dog card displays the `NO VAX` badge, but nowhere does it indicate what pipeline stage the dog is in (Inquiry vs. Meet & Greet vs. Evaluation), nor does it show actionable steps (e.g., "Schedule Meet & Greet" or "Pass Meet & Greet").


3. **No Direct Vaccination Upload / Review Context:** The dog screen has a plain text `"Vaccinations"` link without indicating whether records are uploaded, received, or validated.


4. **Accidental Stage Advancement Has No Reversal:** The UI lacks explicit stage rollback controls if a stage is mistakenly set.



---

# Plan: Meet & Greet / Intake User Experience & Workflow

## 1. Domain Invariants & Rules

1. **Meet & Greet is a Distinct Appointment:**
* It must have an explicit calendar date and time (defaulting to 15 minutes), created either via the Intake Wizard or via an explicit **Schedule Meet & Greet** button on the dog screen.


* It is linked to the `meet_greet` service ($0.00, capacity-exempt).


* It must appear in the dog's **Visits / Appointments** list with a distinct `MEET & GREET` badge.




2. **Strict Gate: Meet & Greet $\rightarrow$ Vaccination Upload $\rightarrow$ Evaluation:**
* **Stage 1 (Inquiry / Meet & Greet):** Can only schedule a Meet & Greet.


* **Meet & Greet Outcome:** Must explicitly record **Passed** (with notes). Once passed, stage advances to **Evaluation Track**.


* **Stage 2 (Paperwork Gate):** The dog cannot book an Initial Evaluation stay until:
* A valid `VaccinationRecord` is added and validated (`validated=True` and `expires_at >= today`).


* Owner COI confirmation is marked received (`coi_confirmed_received=True`).




* **Stage 3 (Initial Evaluation):** Only enabled when M&G is Passed and Paperwork is 100% verified.




3. **Auditable Stage Control & Undo:**
* Provide an explicit **Undo Stage / Revert Stage** action in the dog's actions dropdown to roll back accidental advancements without manual database edits.




4. **No Compatibility Shims:**
* Cleanly refactor the models and views directly without transitional wrapper shims.





---

## 2. Target UI / UX Layout

### A. Dog Profile Screen (`/dogs/<id>/`)

Replace the passive cards with a structured, step-by-step workflow:

```
+-----------------------------------------------------------------------+
|  Lulu  [ INQUIRY / MEET & GREET ]  [ NO VAX ]                         |
|  Owner: David Lundquist (226-688-5370)                                |
+-----------------------------------------------------------------------+
|  INTAKE PIPELINE STATUS                                               |
|                                                                       |
|  [Step 1: Meet & Greet] --> [Step 2: Paperwork] --> [Step 3: Eval]    |
|                                                                       |
|  Current Status: Meet & Greet Required                                |
|  CTA Button: [+ Schedule Meet & Greet] (15 mins, $0)                  |
+-----------------------------------------------------------------------+
|  VACCINATION & COI STATUS                                             |
|                                                                       |
|  Vaccinations:  NO RECORD ON FILE   [+ Upload / Add Record]          |
|  Owner COI:     Confirmed Received (✓)                                |
+-----------------------------------------------------------------------+
|  APPOINTMENTS & VISITS                                                |
|                                                                       |
|  • Aug 30, 2026 10:00 AM - 10:15 AM [ MEET & GREET ]                  |
|    Status: Scheduled  |  [Check-In]  [View Details]                  |
+-----------------------------------------------------------------------+
|  STAGE MANAGEMENT & ACTIONS                                           |
|                                                                       |
|  [Revert to Previous Stage]  |  [Hide Dog]                            |
+-----------------------------------------------------------------------+

```

### B. Post-Meet & Greet Outcome Screen (`/visits/<id>/outcome/`)

When a Meet & Greet visit is checked out or marked completed:

1. Prompts for **Outcome**: `Passed` or `Declined`.


2. Requires **Clinical / Suitability Notes**.


3. If `Passed`:
* Sets dog stage $\rightarrow$ `EVALUATION`.


* Immediately displays the paperwork reminder: *"Meet & Greet Passed. Vaccination records must be uploaded before the 4-hour Initial Evaluation can be booked."*




---

## 3. Step-by-Step Implementation Sequence

### Step 1: Ensure Appointment Persistence & Service Linkage

* Inspect `IntakeWizardForm` in `operations/forms/intake.py` to fix the bug where the created visit fails to persist or bind to `ClientProfile`.


* Ensure the created visit explicitly binds `business_service.slug = 'meet_greet'`, `scheduled_start`, `scheduled_end` (+15 mins if blank), and saves in the same atomic transaction as the dog and owner.



### Step 2: Add Pipeline Header & Action Gates to `dog_detail.html`

* Update `operations/templates/operations/dog_detail.html` (and component sub-templates):
* **Pipeline Card:** Visually show the active step (Step 1: M&G, Step 2: Paperwork, Step 3: Evaluation, Step 4: Approved).


* **Dynamic Action Button:**
* If in `INQUIRY` / `MEET_GREET` without an appointment: show **Schedule Meet & Greet**.


* If M&G is completed & passed, but missing Vax or COI: show **Upload Vaccination Records** (lock evaluation button with an explanation badge).


* If M&G passed + Vax validated + COI confirmed: show **Schedule Initial Evaluation ($15 / 4h)**.


* If Evaluation passed: show **Grant Standard Approval**.







### Step 3: Implement Revert / Undo Stage Endpoint

* Add a dedicated POST endpoint `revert_pipeline_stage` in `operations/views/customers/actions.py`:
* `APPROVED` $\rightarrow$ `EVALUATION`

* `EVALUATION` $\rightarrow$ `MEET_GREET`

* `MEET_GREET` $\rightarrow$ `INQUIRY`



* Expose this in the UI under **Stage Management** on the dog detail screen.

### Step 4: Visits List Rendering

* In `dog_detail.html`, update the **Visits** list loop:
* For each visit, render a prominent badge indicating whether it is a `MEET & GREET`, `EVALUATION`, or `STANDARD STAY` based on `visit.business_service.name`.


* Include start time, end time, status, and a direct link to the visit details/outcome.





### Step 5: Test Verification

* Write end-to-end tests in `operations/tests.py`:
* `test_intake_creates_visible_meet_greet_visit`: Asserts visit is listed on dog profile.


* `test_cannot_book_evaluation_without_vaccination`: Asserts evaluation booking is blocked if `has_current_vaccination` is False.


* `test_revert_pipeline_stage`: Asserts stages can be rolled back safely.