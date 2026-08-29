# Scheduling: Visit booking

**Load for:** create/edit visit, repeat series, clone, stay blockers.  
**Related:** [`capacity.md`](capacity.md), [`pricing.md`](pricing.md), [`calendar_email.md`](calendar_email.md)  
**Forms:** `operations/forms/scheduling/visits.py` (`VisitForm` / `VisitScheduleForm`)  
**Templates:** `visit_form.html` shell + `components/scheduling/` (datetime, repeat, service plans, email confirm, clone)

David books per **dog**. Two free-text fields only — **no multi-step date/time pickers**.

| Field | Example |
| --- | --- |
| Start | `April 11, 2026 5 pm` |
| End | `April 28, 2026 5 pm` |

Plus a required **Service** picker (`business_service`) listing active `BusinessService` rows for the workspace (edit keeps the current service even if inactive). See [`../services.md`](../services.md).

---

## Parse flow

1. Type or dictate (phone keyboard speech-to-text)
2. Blur → `/visits/parse-datetime/` returns formatted preview
3. Tap preview to edit raw text
4. Server parse on submit is authoritative (`datetime_parse.py`)

---

## Standard-stay readiness (create only)

`VisitForm.clean()` calls `ClientProfile.standard_stay_blockers()` on **create** (not edit). Hard form errors (non-field) if any of:

- Pipeline is not **Approved**
- No current validated vaccination (`has_current_vaccination`)
- Owner COI not confirmed (`CustomerOwner.coi_confirmed_received`)
- Dog is **hidden** (`is_hidden`) — cannot book a new stay; existing visits still check in/out

Clone (`clone_to_date`), calendar approve, and **intake Meet & Greet** (`IntakeWizardForm`) bypass the form gate. Do not put this gate on `Visit.save()`.

**Intake Meet & Greet** is a prerequisite catalog service (`slug=meet_greet`, $0, capacity exempt) — distinct from boarding Short Visit. See `services.md` / customers intake. Evaluation (`initial_evaluation`, $15) is seeded for later booking UX.

---

## Repeat (create only — not on edit)

- **Repeat:** none | daily | weekly | weekdays | monthly
- **Every** N days/weeks/months
- **Ends:** number (`5`) or date (`April 15, 2026`) — auto-detected
- Max 52 occurrences (`MAX_OCCURRENCES`). Count of 53+ rejected in `parse_repeat_ends`. An until-date that would yield >52 visits is a `repeat_ends` error — **do not silently clip**. Also reject `len(occurrences) > 52` in `VisitForm.clean()`.
- **Same-dog overlap:** windows must not overlap (`scheduled_start < other.end AND scheduled_end > other.start`). Checked in `Visit.clean()` even when `skip_capacity=True`, and in `VisitForm.clean()`. Back-to-back (end == next start) allowed. Cancelled visits ignored. Different dogs → capacity, not this rule.
- Capacity in `VisitForm.clean()` → non-field errors. After `is_valid()`, `save_all()` uses `visit.save(skip_capacity=True)`. Direct `Visit.save()`, clone, admin still run capacity. Overlap is **not** skipped. Details: [`capacity.md`](capacity.md).
- `VisitForm.save_all()` creates series + visits in one transaction.
- **Edit:** `save(update_fields=['scheduled_start', 'scheduled_end', 'notes', 'business_service', 'updated_at'], skip_capacity=True)` — do not write status, fees, series, or `confirmation_email_sent_at` from a stale instance.
- `VisitSeries` when Repeat is not “Does not repeat” — including a series of **one**. Non-repeating → `series=None`.

---

## Clone past visit

Select completed visit + new start date → copies duration, **local** time-of-day, and `business_service`.

`clone_to_date(new_date)`: localize start → `datetime.combine(new_date, start.time(), tzinfo=…)` → add duration. **Do not** use `datetime.replace(year=, month=, day=)` (31st → short month `ValueError`; DST clock shift). Overnight length preserved. Capacity runs via `Visit.save()`.

---

## Booking confirmation (opt-in)

- Checkbox on create: **Send booking confirmation to {email}** — unchecked by default
- Sends via Gmail OAuth; one email for a whole repeat series; stamps `confirmation_email_sent_at`
- Dog Visits list: muted **emailed M j**, or **Send email** → `POST /visits/<id>/send-confirmation/` (already-sent = no-op)
- OAuth failures → `GmailSendError` / `VisitEmailError`; **visit stays booked**; never 500

MIME / VEVENT / iCal details: [`calendar_email.md`](calendar_email.md).
