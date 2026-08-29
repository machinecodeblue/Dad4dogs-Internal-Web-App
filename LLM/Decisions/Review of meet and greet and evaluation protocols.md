# Decision: Review of meet and greet and evaluation protocols

**Status:** accepted — dedicated schedule screens landed  
**Live spec:** `customers.md`, `scheduling/booking.md`  
**What we took:** `MeetGreetScheduleForm` / `EvaluationScheduleForm`; URLs `/dogs/<id>/meet-greet/add/` and `/evaluation/add/`; VisitForm boarding-only; fixed 15m / 4h; no repeat/catalog on intake appointments.  
**What we left:** Agenda badges.  
**Why:** M&G and Evaluation must not share the recurring stay booking UI.

---

### What the Rendered HTML Reveals

The rendered template shows that **Meet & Greet** is using the generic `visit_form.html` interface instead of a purpose-built intake workflow:

1. **Repeat Series Controls on a One-Off Prerequisite:** The form displays daily/weekly/monthly repeat options. A Meet & Greet (and an Initial Evaluation) is a singular prerequisite appointment, not a recurring service schedule.


2. **Exposing the Full Service Catalog:** The `<select>` dropdown lets you choose *Short Visit*, *Daytime Visit*, or *Overnight Stay* while ostensibly on a screen titled *"Schedule Meet & Greet — Lulu"*.


3. **Freeform End Time Instead of a Fixed Appointment:** The form exposes an open `end_at` field, inviting manual end-time entry rather than enforcing the fixed 15-minute window (or 4-hour window for an Evaluation).



---

### The Clean Architecture Fix (No Shims, Explicit Workflows)

Meet & Greet and Initial Evaluation are **lifecycle intake appointments**, not generic boarding bookings. They require dedicated, single-purpose booking views and forms rather than overloading `VisitForm` with dynamic conditional visibility.

```
operations/
├── forms/
│   └── intake/
│       ├── meet_greet.py       # MeetGreetScheduleForm (Date/Start time only -> auto +15m, $0, no repeat)
│       └── evaluation.py       # EvaluationScheduleForm (Date/Start time only -> auto +4h, $15, no repeat)
└── views/
    └── intake/
        ├── meet_greet.py       # schedule_meet_greet, meet_greet_outcome
        └── evaluation.py       # schedule_evaluation, evaluation_outcome

```

---

### 1. Dedicated `MeetGreetScheduleForm`

Strip away the repeat machinery, service picker, and arbitrary end dates:

* **Fields:**
* `start_at` (Natural language or time picker, e.g., *"Aug 30, 2026 10 am"*)


* `notes` (Optional staff notes)


* `send_confirmation_email` (Checkbox)




* **Enforced Invariants in `clean()` / `save()`:**
* `repeat_frequency` is strictly locked to `none` (no `VisitSeries` allowed).


* `business_service` is hardcoded to `meet_greet` ($0.00, `capacity_exempt=True`).


* `scheduled_end` is automatically calculated server-side as `scheduled_start + timedelta(minutes=15)`.


* Validates that the dog is currently in `INQUIRY` or `MEET_GREET` stage and has no open, uncompleted M&G appointments.





---

### 2. Dedicated `EvaluationScheduleForm`

* **Fields:**
* `start_at` (Date & start time)


* `notes` (Optional notes)


* `send_confirmation_email` (Checkbox)




* **Enforced Invariants in `clean()` / `save()`:**
* `repeat_frequency` is strictly locked to `none`.


* `business_service` is hardcoded to `initial_evaluation` ($15.00 flat).


* `scheduled_end` is automatically calculated server-side as `scheduled_start + timedelta(hours=4)`.


* Hard gate: Requires a prior **Passed** Meet & Greet appointment, `has_current_vaccination == True`, and `coi_confirmed_received == True`.





---

### 3. Dedicated Template: `meet_greet_schedule.html`

The screen presents only what is needed to book the appointment:

```html
<div class="card">
    <p class="muted"><a href="{% url 'dog_detail' dog.id %}">← {{ dog.dog_name }}</a></p>
    <h2>Schedule Meet &amp; Greet — {{ dog.dog_name }}</h2>
    <p class="muted">15-minute suitability interview. Free of charge.</p>
</div>

<div class="card">
    <form method="post">
        {% csrf_token %}
        
        <!-- Start Time Field with Natural Language Assist -->
        <div class="datetime-field editing" id="start-field">
            <label for="id_start_at">Appointment Date &amp; Start Time</label>
            <input type="text" name="start_at" placeholder="e.g. Tomorrow 10 am" class="datetime-text-input" required>
            <p class="muted" style="font-size: 0.85rem; margin-top: 0.25rem;">
                Duration is automatically set to 15 minutes.
            </p>
        </div>

        <!-- Optional Notes -->
        <label for="id_notes" style="margin-top: 1rem; display: block;">Notes (optional)</label>
        <textarea name="notes" rows="2" placeholder="Specific owner requests or gate instructions..."></textarea>

        <!-- Confirmation Email -->
        <div class="email-confirm-card">
            <label for="id_send_confirmation_email">
                <input type="checkbox" name="send_confirmation_email" id="id_send_confirmation_email">
                <span><strong>Send booking confirmation to {{ dog.customer_owner.owner_email }}</strong></span>
            </label>
        </div>

        <div class="actions" style="margin-top: 1rem;">
            <button type="submit" class="btn btn-primary">Confirm Meet &amp; Greet</button>
            <a href="{% url 'dog_detail' dog.id %}" class="btn btn-outline">Cancel</a>
        </div>
    </form>
</div>

```

---

### 4. Visibility & Pipeline State on the Dog Profile Screen

On `/dogs/<id>/`:

1. **Clear Stage Display:** Shows a badge (e.g., `MEET & GREET REQUIRED`, `AWAITING PAPERWORK`, `READY FOR EVALUATION`, `APPROVED`).


2. **Context-Sensitive Actions:**
* If in `INQUIRY` / `MEET_GREET` without an appointment $\rightarrow$ Display primary button: **`[Schedule Meet & Greet]`** leading to `/dogs/<id>/meet-greet/add/`.


* If Meet & Greet is scheduled $\rightarrow$ Display appointment details card with status and a direct **`[Record Outcome]`** button.


* If Meet & Greet is **Passed** but no vax records exist $\rightarrow$ Lock the evaluation button and display an alert: **`[Upload Vaccination Record to Unlock Evaluation]`**.




3. **Visits Card Segregation:**
* Renders Meet & Greet and Evaluation events with clear badges (`MEET & GREET`, `EVALUATION`) so they stand apart from standard daycare and boarding stays.





Separating these intake milestones from generic visit creation enforces the required business rules without complex conditional logic in the general booking views.