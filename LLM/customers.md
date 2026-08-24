# Domain: Customers

**Covers:** owners, dogs, COI, vaccinations, emergency contacts, veterinary contacts, Google Contacts import, pipeline per dog.

**Code packages:** `operations/models/customers.py`, `forms/customers.py`, `views/customers.py`  
**Services:** `operations/services/contacts.py`, `addresses.py`, `phones.py`, `feed_slugs.py`, `feed_access.py`  
**Customer feed & social:** see [`feed.md`](feed.md) — private feed (react, comment, share) and public `/feed/share/<token>/` (re-share, download)

---

## 1. Data Model

| Model | Key | Owns |
|-------|-----|------|
| `CustomerOwner` | `owner_email` (unique) | COI, primary owner contact, emergency/pickup contacts |
| `ClientProfile` | `owner_email` + `dog_name` (unique) | Pipeline, visits, notes, **per-dog vet contacts**, feed URL credentials |
| `VaccinationRecord` | FK → `ClientProfile` | Vet papers, expiry, validation |
| `FeedAccessLog` | FK → `ClientProfile` | Anonymous feed page views (visitor cookie) |

### Rules
1. A customer may have **zero dogs** until David explicitly adds one.
2. **Pipeline is per dog**, not per customer.
3. **COI is per customer** — all dogs under the same email share COI status.
4. **Vaccinations are per dog** — never on the customer screen.
5. **Emergency contacts and authorized pickup are per owner** — shared across all dogs.
6. **Veterinary contacts and care authorization are per dog** — act immediately without asking the owner which vet to call.
7. `is_valid_dog_name()` rejects TBD, UNKNOWN, and dog name = owner's first name.
8. **Never hard-delete a dog from the UI.** `is_hidden` removes them from the client list; visits and photos stay. Hide/unhide only.

---

## 2. Contact Collection Strategy

Operational contact data is split between **Owner Data** (`CustomerOwner`) and **Dog-Specific Data** (`ClientProfile`).

### 2.1 Primary Owner Contact (`CustomerOwner`)

| Field | Purpose |
|-------|---------|
| `owner_name` | Full name — billing, statements, waivers |
| `owner_salutation` | Pronouns or salutation (optional) |
| `owner_email` | Unique database key — stored lowercase; form rejects duplicates (`iexact`) instead of a 500 |
| `owner_phone` | **Primary mobile — required on form** — stored as 10-digit NANP (`4165550100`); tap-to-call uses `tel:+1…` |
| `address_street` | Street number and name (e.g. 191 Grey Street) |
| `address_unit` | Optional unit / apt / suite |
| `address_city` | City |
| `address_province` | Two-letter code (`ON` … `YT`); blank allowed |
| `address_postal_code` | Canadian postal code, stored as `A1A 1A1` |
| `home_address` | Formatted cache of the structured fields; also holds **legacy** free text until the record is re-saved |

Display helpers on `CustomerOwner`: `formatted_address` (multiline), `address_oneline`, `address_maps_url` (Google Maps search). `save()` rebuilds `home_address` when any structured part is set. Address may be entirely blank; if any part is filled, street, city, province, and postal are required (unit stays optional).

### 2.2 Emergency & Secondary Contact (`CustomerOwner`)

| Field | Purpose |
|-------|---------|
| `emergency_contact_name` | Trusted fallback if primary owner unreachable |
| `emergency_contact_phone` | Direct mobile — tap-to-call on customer/dog detail |
| `emergency_contact_relationship` | Context for logistics (e.g. "Neighbor with house key") |
| `authorized_pickup_names` | Multiline text — one name per line; custody authorization. `CustomerOwnerForm.clean_authorized_pickup_names()` strips blank lines and surrounding spaces before save. |

Property: `authorized_pickup_list` — parsed non-empty stripped lines for templates.

### 2.3 Medical & Veterinary Contact (`ClientProfile` — per dog)

| Field | Purpose |
|-------|---------|
| `vet_clinic_name` | Primary clinic (e.g. Grey Street Animal Hospital) |
| `vet_name` | Doctor who knows the dog's history |
| `vet_clinic_phone` | Tap-to-call in dog-detail Veterinary disclosure; check-in uses it if no emergency vet |
| `emergency_vet_clinic` | Preferred 24-hour hospital after regular hours |
| `emergency_vet_phone` | Tap-to-call emergency vet |
| `vet_care_authorization` | Dollar cap or directive (e.g. approve $500 triage before contacting owner) |

`VaccinationRecord.vet_clinic` remains for **paper records** per vaccination upload — separate from standing vet contacts on the dog profile.

### Denormalization
`ClientProfile` still copies `owner_name`, `owner_email`, `owner_phone` from `CustomerOwner` on dog save and when customer is edited — supports visit/email queries without joins.

---

## 3. CustomerOwner COI fields

- `coi_sent_at`, `coi_confirmed_received`, `coi_confirmed_at`
- Methods: `mark_coi_sent()`, `mark_coi_received()`, `for_client()` (read-only lookup), `ensure_for_client()` (create on write paths / form save only)

---

## 4. ClientProfile pipeline & feed

### Pipeline
`INQUIRY` → `MEET_GREET` → `EVALUATION` → `APPROVED`  
Method: `advance_pipeline()` on dog screen — returns `False` (no write) if already Approved; the view flashes info, not success. The Advance button is hidden at Approved.

### Customer feed fields
- `feed_secret` — speakable unique slug (CV syllables, e.g. `movakitu`)
- `feed_dog_slug` — from dog name (e.g. `lulu`)
- Methods: `ensure_feed_credentials()`, `feed_url(create=True)`, `regenerate_feed_secret()`, `sync_feed_dog_slug()`. GET screens call `feed_url(create=False)` so missing credentials stay missing.
- Auto-created on first access; included in booking email when `PUBLIC_SITE_URL` is set

### VaccinationRecord
- `expires_at` is **required**
- Form: `expires_at` must be on or after `received_at` (`VaccinationRecordForm.clean()`) — clerical swap of the two dates is rejected before save
- Past `expires_at` (after received) is allowed so old papers can be logged; `add_vaccination` flashes a warning that the dog is not current
- Current vax = `validated=True` AND `expires_at >= today` (`has_current_vaccination`) — this is the standard-stay gate
- Latest validated expiry = `Max(expires_at)` among `validated=True` records (`current_vaccination_expires_at`)
- `vaccination_status`: `ok` | `expiring` | `expired` | `missing`
  - `expiring` = current (`expires_at >= today`) **and** `expires_at <= today + 30` (`VAX_EXPIRY_WARNING_DAYS`)
  - `expired` = latest validated `expires_at < today`
  - `missing` = no validated record
  - `ok` = current and more than 30 days out
- QuerySet: `with_vaccination_expiry()`, `filter_vaccination_status(status)`, `vaccination_status_counts()`
- Methods: `mark_validated()`; `is_expired`; `is_expiring_soon` (not expired, within 30 days)

---

## 5. Screens & URLs

| Screen | URL | Contents |
|--------|-----|----------|
| Client list | `/clients/` | Compact dog rows (`Dog · Owner · phone`); filters and extra create links in disclosures. `?stage=` / `?vax=`. Orphans under **Dogs without a customer**. |
| Create customer from dog | `POST /dogs/<id>/create-customer/` | `ensure_for_client()` for an orphan dog, then customer detail |
| **New Client & Dog** | `/clients/intake/` | One POST: owner + first dog + vet + optional Meet & Greet (`IntakeWizardForm`). Atomic. M&G visit **skips** standard-stay Approved/vax/COI gate. Pipeline → Meet & Greet if times set, else Inquiry. |
| Add customer | `/clients/add/` | Owner + emergency contacts — no dog |
| Customer | `/customers/<id>/` | Name, Call, emergency call. Address/maps, pickup, COI timestamps, hide/edit sit in `<details>`. Dogs are compact rows. |
| Edit customer | `/customers/<id>/edit/` | Primary + structured address (street / unit / city / province / postal) + emergency |
| Add dog | `/customers/<id>/add-dog/` | Dog profile + vet contacts; pipeline starts at Inquiry |
| Dog | `/dogs/<id>/` | Name, Call owner, emergency-vet call (max two primary buttons). Visits compact + Schedule stay. Address, clinic, feed, Hide/vCard in `<details>`. |
| Hide / unhide dog | `POST /dogs/<id>/hide/` · `POST /dogs/<id>/unhide/` | Soft-hide from client list. Legacy `/dogs/<id>/delete/` aliases hide. |
| Edit dog | `/dogs/<id>/edit/` | Dog profile + veterinary section |
| Regenerate feed | `POST /dogs/<id>/feed/regenerate/` | New `feed_secret` — old links stop working |
| Vaccinations | `/dogs/<id>/vaccinations/` | List, add, validate — dog only |
| Check-in | `/checkin/` | Per-visit owner phone + emergency (or clinic) tap-to-call. **Check In**, or **Log Moment** + **Check Out**. |
| vCard export | `/clients/<id>/vcard/` | Per-dog `.vcf` for Google |
| Contact sync | `/contacts/sync/` | CSV upload hub |
| Import preview | `/contacts/import/` | Analysis before DB write |
| Import confirm | `/contacts/import/add/` | POST selected rows |

### Legacy redirects
- `/clients/<dog_pk>/` → customer view for that dog's owner
- `/clients/<dog_pk>/edit/` → dog edit

### Client list badges (actionable only — no green OK; at most two per row)
| Badge | When shown |
|-------|------------|
| VAX + date (amber) | Current vax expires within 30 days |
| VAX EXPIRED (red) | Latest validated record expired |
| VAX (amber) | No validated record |
| Pipeline (amber) | Dog is not Approved |

COI warnings live on the **customer** screen, not the compact list (keeps rows at ≤2 badges).

---

## 6. Forms

| Form | File | Purpose |
|------|------|---------|
| `CustomerOwnerForm` | `forms/customers.py` | Primary + **structured address** (all-or-nothing except unit) + emergency + pickup; **phone required** and NANP-validated; email lowercased and unique; pickup names stripped of blank lines. On edit, empty structured fields are prefilled from `parse_legacy_address(home_address)` — never dump a multiline blob into the street input. Empty province is `''`; aliases (`Ontario`) coerce to `ON`. |
| `DogProfileForm` | `forms/customers.py` | Dog name via `is_valid_dog_name()`; duplicate `dog_name` error is on that field; vet phones NANP-validated. `save()` copies owner name/email/phone (resolves owner on edit if omitted) and always runs `ensure_feed_credentials(save=False)` so `commit=False` callers still get a secret/slug on the instance. |
| `VaccinationRecordForm` | `forms/customers.py` | `fixed_client` pins the dog (POST cannot swap); `expires_at >= received_at`; `papers_received` checkbox `required=False` (unchecked = False); past expiry still saves with a warning |
| `IntakeWizardForm` | `forms/intake.py` | Owner + dog + vet + optional M&G datetimes; `save()` returns `(owner, dog, visit)`; inherits owner phone rules + vet phones |

---

## 7. Google Contacts Import

**Never auto-import the full CSV.** Preview first, David selects rows.

### Flow
1. Export from Google as CSV (`Data samples/google_contacts.csv` = format reference)
2. Upload at `/contacts/sync/`
3. `contacts.py` parses + analyzes → session key `contact_import_analysis`
4. Preview: name flags, duplicates, editable owner/dog/phone fields
5. POST selected rows → creates `CustomerOwner`; `ClientProfile` only if `is_valid_dog_name()`

### Import principles
- Person-shaped name with no dog in notes → **customer only** (`CUSTOMER ONLY` badge)
- Email matches existing customer with no dogs → `CUSTOMER ON FILE`
- Never create a dog from owner's first name
- Flag unreliable names in **Names to Verify** section
- Emergency/vet fields are filled in manually after import — not parsed from Google CSV today

### Export (Dad4dogs → Google)
- Per dog vCard at `/clients/<id>/vcard/`
- Includes `NOTE: Dog: <name>`
- Includes `ADR;TYPE=HOME` from the owner's structured address when present

### Key service functions (`contacts.py`)
`parse_google_csv`, `analyze_import`, `import_selected_contacts`, `build_vcard`, `is_valid_dog_name`, `assess_name_quality`

### Address helpers (`addresses.py`)
`format_address`, `normalize_postal_code`, `normalize_province`, `parse_legacy_address`, `maps_search_url` — Canadian postal + province only.

### Phone helpers (`phones.py`)
`normalize_phone` (digits, strip leading `1`), `validate_phone` (require 10-digit NANP; area/exchange cannot start with 0 or 1), `format_phone` (`(416) 555-0100`), `tel_href` (`tel:+14165550100`), `e164`.  
`NanpPhoneFormMixin` applies this to `owner_phone` (required), `emergency_contact_phone`, `vet_clinic_phone`, `emergency_vet_phone`. Empty optional phones stay empty. Import still uses `normalize_phone` for duplicate matching; stored import phones are validated when they look like NANP.

---

## 8. Views (customers.py)

Every view declares allowed methods (`@require_GET`, `@require_POST`, or `@require_http_methods(['GET', 'POST'])`). Wrong verbs return **405**.

GET paths do **not** call `ensure_for_client()` or `ensure_feed_credentials()`. Missing owner → 404. `customer_edit` captures `old_email` **before** `is_valid()` (Django mutates the instance during model validation), then wraps owner save + dog denormalized copy in `transaction.atomic()`.

`?stage=` must be a `PipelineStage` value or it is ignored (same as invalid `?vax=`). vCard filenames keep only `A-Za-z0-9_-`. Import `selected_rows` skip non-integers instead of 500.

`client_list`, `client_create`, `customer_edit`, `customer_detail`, `customer_add_dog`, `dog_edit`, `dog_detail`, `dog_delete`, `dog_create_customer`, `dog_feed_regenerate`, `dog_vaccinations`, `update_coi`, `add_vaccination`, `validate_vaccination`, `advance_pipeline`, `contact_sync`, `contact_import_preview`, `contact_import_selected`, `client_vcard`, plus legacy redirects.

Public feed view lives in `views/customer_feed.py` — not in this package.

---

## 9. Tests

`CustomerOwnerFormTests`, `AddressHandlingTests`, `CognitiveLoadUXTests`, `DogProfileFormTests`, `IntakeWizardTests`, `ContactDataTests`, `CustomerEditTests`, `CustomerViewsHttpTests`, `ContactSyncTests`, `ComplianceTests`, `VaccinationExpiryViewTests`, `FeedSlugTests`, `CustomerFeedTests` in `operations/tests.py`.

---

## 10. Migrations

| Migration | Contents |
|-----------|----------|
| `0003_owner_coi_and_vax_expiry` | `CustomerOwner` + COI migration |
| `0014_owner_emergency_and_vet_contacts` | Owner emergency/pickup + per-dog vet fields |
| `0017_structured_home_address` | `address_street` / `unit` / `city` / `province` / `postal_code`; copies legacy `home_address` via `parse_legacy_address()` |
| `0018_backfill_owners_and_feed_credentials` | Create missing `CustomerOwner` rows and fill blank feed secret/slug |
| `0019_clientprofile_is_hidden` | Soft-hide flag; UI never hard-deletes dogs |

---

## 11. Not Yet Built

- PDF/image upload for vet papers
- Email/SMS reminders before `expires_at` — dashboard counts + `/clients/?vax=expiring` are done; outbound notify is not
- Hard block scheduling until compliance + contact completeness — **partially done**: `VisitForm` create requires Approved + current vax + COI received (`standard_stay_blockers()`). Clone and calendar import still ungated. No emergency-phone / contact-completeness gate yet. Expiring (still current) dogs are **not** blocked — chase papers via the 30-day list.
- Live Google People API sync (file-based CSV only today)
- Multiple emergency contacts per owner (single fallback contact today)
- PWA push to `owner_phone` on new photos (phone field is the hook)