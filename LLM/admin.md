# Domain: Admin

**Covers:** baseline Dad4dogs business details — identity, address, hours, phone numbers, and (planned) stable document storage.

**Code packages:** `operations/models/business.py`, `forms/business.py`, `views/business.py`  
**Template:** `operations/templates/operations/business_settings.html`

---

## 1. Purpose

David needs a single place to maintain **stable business facts** that rarely change — contact info, hours, and eventually certificates and other documents. This is separate from:

- **Customer COI** (`CustomerOwner`) — per-client insurance confirmation
- **Django admin** (`/admin/`) — low-level data editing and auth login

The **Settings** screen (`/settings/`) is the day-to-day admin tool for business baseline data.

---

## 2. Data Model

### `BusinessProfile` (singleton)

Exactly **one row** in the database. Always access via `BusinessProfile.load()` — never create multiple profiles.

| Field | Purpose |
|-------|---------|
| `business_name` | Display name (default: `Dad4dogs`) |
| `business_email` | Primary business email for client communications |
| `address` | Full mailing or service address (free text) |
| `hours_of_operation` | When clients can reach you or drop off/pick up (free text) |
| `main_phone` | Primary business line |
| `secondary_phone` | Alternate line (e.g. secondary mobile) |
| `emergency_phone` | Number clients call if there is an urgent problem |
| `updated_at` | Last save timestamp |

Internal: `singleton_key = 'X'` (unique) enforces single-row pattern.

### Rules
1. Use `BusinessProfile.load()` everywhere — views, services, templates.
2. Do not add per-customer fields here; customer data stays in `customers` domain.
3. Free-text `address` and `hours_of_operation` — mobile-friendly, voice-to-text compatible.
4. When wiring into emails or PDFs, read from `BusinessProfile.load()`; do not hardcode David's details.

---

## 3. Screens & URLs

| Screen | URL | Contents |
|--------|-----|----------|
| Business settings | `/settings/` | Identity, location/hours, three phone numbers |

Bottom nav **Settings** links here.

Django admin also exposes **Business profile** for the same singleton record (`operations/admin.py`).

---

## 4. Forms

| Form | File | Purpose |
|------|------|---------|
| `BusinessProfileForm` | `forms/business.py` | Edit all baseline fields |

---

## 5. Views (business.py)

| View | Purpose |
|------|---------|
| `business_settings` | GET/POST edit form; redirects back on save with success message |

`@login_required` — same auth as all operational views.

---

## 6. Integration Points

Pull from `BusinessProfile.load()` — never hardcode David's business details.

| Consumer | Fields | Status |
|----------|--------|--------|
| Booking iCal (`visit_email.py` → `generate_booking_ics`) | `address` → `LOCATION`; `business_email` + `business_name` → `ORGANIZER` | **Done** |
| Booking confirmation email (plain text) | Schedule, notes; feed URL when `PUBLIC_SITE_URL` set | **Done** (feed link) |
| Statement emails (`billing.md`) | `business_name`, `business_email`, phones, hours | Not wired |
| iCal outbound `/ical/` | `business_name`, `address` | Partial |
| Client-facing PDFs or COI sends | Uploaded business documents (see §7) | Not started |

### BusinessProfile helper properties
- `calendar_organizer_email`, `calendar_organizer_name`, `calendar_location` — used by booking invites

`business_email` is **required** before sending a booking calendar invite.

---

## 7. Not Yet Built

| Item | Notes |
|------|-------|
| Document uploads | David's Certificate of Insurance and other stable business files |
| Document list/replace UI | On Settings screen or sub-page |
| `MEDIA_ROOT` / file storage config | Required before uploads |
| Use profile in statement emails | Read phones, hours, address from singleton in email body |
| Business logo or letterhead asset | Optional future field |

### Document upload guidance (when built)
- Store under `operations/models/business.py` or a sibling `BusinessDocument` model
- Keep uploads in a gitignored media path
- Do not confuse with **customer COI** tracking on `CustomerOwner`

---

## 8. Tests

`BusinessProfileTests`, `BusinessSettingsViewTests` in `operations/tests.py`.

Add tests when:
- Document upload is added
- Services start reading `BusinessProfile` for email bodies or PDFs

---

## 9. Migration

`operations/migrations/0007_business_profile.py` — creates `BusinessProfile`.