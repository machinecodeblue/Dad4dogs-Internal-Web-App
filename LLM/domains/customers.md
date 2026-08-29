# Domain: Customers

**Covers:** owners, dogs, COI, vaccinations, emergency contacts, veterinary contacts, pipeline per dog; Google Contacts import / vCard — see **[`contacts.md`](https://www.google.com/search?q=contacts.md)**.

**Code packages:** `operations/models/customers/` (`owners.py`, `dogs.py`, `vaccinations.py`, `telemetry.py`, `constants.py`, `__init__.py`), `forms/customers.py`, `operations/views/customers/` (`clients.py`, `intake.py`, `vaccinations.py`, `contacts.py`, `actions.py`, `__init__.py`)

**Services:** `operations/services/contacts/` (see `contacts.md`), `addresses.py`, `phones.py`; feed secrets/slugs via `feed_interactions/` (see `feed.md`)

**Customer feed & social:** see [`feed.md`](https://www.google.com/search?q=feed.md) — private feed (react, comment, share) and public `/feed/share/<token>/` (re-share, download)

---

## 1. Data Model (`operations/models/customers/`)

All models inherit from `TenantAwareModel` (`tenant_id` foreign key).

| Model | Submodule | Unique Key | Owns |
| --- | --- | --- | --- |
| `CustomerOwner` | `owners.py` | `tenant` + `owner_email` | COI, primary owner contact, emergency/pickup contacts |
| `ClientProfile` | `dogs.py` | `tenant` + `owner_email` + `dog_name` | Pipeline, visits, notes, **per-dog vet contacts**, feed URL credentials |
| `VaccinationRecord` | `vaccinations.py` | PK (FK $\rightarrow$ `ClientProfile`) | Vet papers, expiry date, validation timestamp |
| `FeedAccessLog` | `telemetry.py` | PK (FK $\rightarrow$ `ClientProfile`) | Anonymous feed page views (visitor cookie logging) |

### Rules

1. A customer may have **zero dogs** until David explicitly adds one.
2. **Pipeline is per dog**, not per customer.
3. **COI is per customer** — all dogs under the same email share COI status.
4. **Vaccinations are per dog** — never on the customer screen.
5. **Emergency contacts and authorized pickup are per owner** — shared across all dogs.
6. **Veterinary contacts and care authorization are per dog** — act immediately without asking the owner which vet to call.
7. `is_valid_dog_name()` rejects TBD, UNKNOWN, and dog name = owner's first name.
8. **Never hard-delete a dog from the UI.** `is_hidden` removes them from the client list; visits and photos stay. Hide/unhide only.
9. **Import Layering Compliance:** `ClientProfile` methods (`ensure_feed_credentials`, `sync_feed_dog_slug`, `regenerate_feed_secret`) must **lazy-import** slug helpers from leaf module `operations.services.feed_interactions.slugs` (never from `feed_interactions` root `__init__.py`).

---

## 2. Contact Collection Strategy

Operational contact data is split between **Owner Data** (`CustomerOwner`) and **Dog-Specific Data** (`ClientProfile`).

### 2.1 Primary Owner Contact (`CustomerOwner` — `owners.py`)

| Field | Purpose |
| --- | --- |
| `owner_name` | Full name — billing, statements, waivers |
| `owner_salutation` | Pronouns or salutation (optional) |
| `owner_email` | Unique database key per tenant — stored lowercase; form rejects duplicates (`iexact`) instead of a 500 |
| `owner_phone` | **Primary mobile — required on form** — stored as 10-digit NANP (`4165550100`); tap-to-call uses `tel:+1…` |
| `address_street` | Street number and name (e.g. 191 Grey Street) |
| `address_unit` | Optional unit / apt / suite |
| `address_city` | City |
| `address_province` | Two-letter code (`ON` … `YT`); blank allowed |
| `address_postal_code` | Canadian postal code, stored as `A1A 1A1` |
| `home_address` | Formatted cache of the structured fields; also holds **legacy** free text until the record is re-saved |

Display helpers on `CustomerOwner`: `formatted_address` (multiline), `address_oneline`, `address_maps_url` (Google Maps search). `save()` rebuilds `home_address` when any structured part is set. Address may be entirely blank; if any part is filled, street, city, province, and postal are required (unit stays optional).

### 2.2 Emergency & Secondary Contact (`CustomerOwner` — `owners.py`)

| Field | Purpose |
| --- | --- |
| `emergency_contact_name` | Trusted fallback if primary owner unreachable |
| `emergency_contact_phone` | Direct mobile — yellow Call on the **Emergency & Pickups** card, grouped with that person’s name; dog detail still has emergency **vet** |
| `emergency_contact_relationship` | Context for logistics (e.g. "Neighbor with house key") |
| `authorized_pickup_names` | Multiline text — one name per line; custody authorization. `CustomerOwnerForm.clean_authorized_pickup_names()` strips blank lines and surrounding spaces before save. |

Property: `authorized_pickup_list` — parsed non-empty stripped lines for templates.

### 2.3 Medical & Veterinary Contact (`ClientProfile` — `dogs.py`)

| Field | Purpose |
| --- | --- |
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

## 3. CustomerOwner COI Fields

* `coi_sent_at`, `coi_confirmed_received`, `coi_confirmed_at`
* Methods: `mark_coi_sent()`, `mark_coi_received()`, `for_client()` (read-only lookup), `ensure_for_client()` (create on write paths / form save only)

**UI (customer summary only):** COI is proof that papers exist, not a section to study. If `coi_status` is `not_sent` or `sent`, show a warning plus Mark sent / Confirm received on the **profile card**. If `received`, show a **✓** beside the owner name (`details.coi-mark`; tap for date / Clear confirmation). Do **not** give COI its own card. Do **not** put a COI badge on the client list.

---

## 4. ClientProfile Pipeline & Feed

### Pipeline

`INQUIRY` $\rightarrow$ `MEET_GREET` $\rightarrow$ `EVALUATION` $\rightarrow$ `APPROVED`

Method: `advance_pipeline()` on dog screen — returns `False` (no write) if already Approved; the view flashes info, not success. The Advance button is hidden at Approved.

### Customer Feed Credentials

* `feed_secret` — speakable unique slug (CV syllables, e.g. `squeakytiki`)
* `feed_dog_slug` — from dog name (e.g. `lulu`)
* Methods: `ensure_feed_credentials()`, `feed_url(create=True)`, `regenerate_feed_secret()`, `sync_feed_dog_slug()`. GET screens call `feed_url(create=False)` so missing credentials stay missing.
* Auto-created on first access; included in booking email when `PUBLIC_SITE_URL` is set.

### Vaccination Tracking (`vaccinations.py` & `constants.py`)

* `expires_at` is **required**
* Form: `expires_at` must be on or after `received_at` (`VaccinationRecordForm.clean()`) — clerical swap of the two dates is rejected before save
* Past `expires_at` (after received) is allowed so old papers can be logged; `add_vaccination` flashes a warning that the dog is not current
* Current vax = `validated=True` AND `expires_at >= today` (`has_current_vaccination`) — this is the standard-stay gate
* Latest validated expiry = `Max(expires_at)` among `validated=True` records (`current_vaccination_expires_at`)
* `vaccination_status`: `ok` | `expiring` | `expired` | `missing`
* `expiring` = current (`expires_at >= today`) **and** `expires_at <= today + 30` (`VAX_EXPIRY_WARNING_DAYS`)
* `expired` = latest validated `expires_at < today`
* `missing` = no validated record
* `ok` = current and more than 30 days out


* QuerySet (`ClientProfileQuerySet`): `with_vaccination_expiry()`, `filter_vaccination_status(status)`, `vaccination_status_counts()`
* Methods on `VaccinationRecord`: `mark_validated()`; `is_expired`; `is_expiring_soon`

---

## 5. Screens & URLs

| Screen | URL | Contents |
| --- | --- | --- |
| Client list | `/clients/` | **Dense owner-first list** (not per-client cards). Search (client-side, owner + dog names). **+ New Client** $\rightarrow$ intake only. Stage/vax filters inline. Rows: `Last, First — phone`; dogs nested with badges + text **Book**. Owner name $\rightarrow$ customer summary. Google Contact Sync lives on **Settings**, not here. |
| Create customer from dog | `POST /dogs/<id>/create-customer/` | `ensure_for_client()` for an orphan dog, then customer detail |
| **New Client & Dog** | `/clients/intake/` | One POST: owner + first dog + vet + optional Meet & Greet (`IntakeWizardForm`). Atomic. M&G visit **skips** standard-stay Approved/vax/COI gate. Pipeline $\rightarrow$ Meet & Greet if times set, else Inquiry. |
| Add customer | `/clients/add/` | Owner + emergency contacts — no dog |
| Customer | `/customers/<id>/` | Three labeled cards. **Primary owner contact:** name + Edit, phone + compact Call, email, address/maps, COI warn or **✓**. **Emergency & Pickups:** name labeled “Emergency contact”, yellow Call beside that phone, authorized pickup listed. **Dogs:** compact rows + Add dog. No More actions, no dedicated COI card, no SMS. |
| Edit customer | `/customers/<id>/edit/` | Primary + structured address (street / unit / city / province / postal) + emergency |
| Add dog | `/customers/<id>/add-dog/` | Dog profile + vet contacts; pipeline starts at Inquiry |
| Dog | `/dogs/<id>/` | Labeled cards. **Dog:** name + Edit, **Vaccinations** link (records page — not the Edit form), owner + Call, drop-off. **Veterinary:** emergency vet + clinic. **Visits** + Schedule stay only when the dog is bookable; each visit shows **emailed** date or **Send email**. Feed / hide / vCard in More actions. |
| Hide / unhide dog | `POST /dogs/<id>/hide/` · `POST /dogs/<id>/unhide/` | Soft-hide from client list. Legacy `/dogs/<id>/delete/` aliases hide. |
| Edit dog | `/dogs/<id>/edit/` | Dog profile + veterinary **contacts** only. Link to **Vaccinations** for papers/expiry. |
| Regenerate feed | `POST /dogs/<id>/feed/regenerate/` | New `feed_secret` — old links stop working |
| Vaccinations | `/dogs/<id>/vaccinations/` | List, add, validate — dog only |
| Check-in | `/checkin/` | Per-visit owner phone + emergency (or clinic) tap-to-call. **Check In**, or **Log Moment** + **Check Out**. Correct late tap arrival/departure via compact datetime fields (`update_actual_times`); completed visits stay listed under **Checked out today**. |
| vCard export | `/clients/<id>/vcard/` | Per-dog `.vcf` for Google (legacy) |
| Contact sync | `/contacts/sync/` | CSV upload hub (legacy) |
| Import preview | `/contacts/import/` | Analysis before DB write (legacy) |
| Import confirm | `/contacts/import/add/` | POST selected rows (legacy) |

### Client List Badges (Actionable Only — At Most Two Per Row)

| Badge | When shown |
| --- | --- |
| VAX + date (amber) | Current vax expires within 30 days |
| VAX EXPIRED (red) | Latest validated record expired |
| NO VAX (amber) | No validated record — do not label this `VAX` |
| Pipeline (amber) | Dog is not Approved |

---

## 6. Forms (`forms/customers.py` & `forms/intake.py`)

| Form | File | Purpose |
| --- | --- | --- |
| `CustomerOwnerForm` | `forms/customers.py` | Primary + **structured address** + emergency + pickup; **phone required** and NANP-validated; email lowercased and unique; pickup names stripped of blank lines. Prefills empty structured fields from `parse_legacy_address(home_address)` on edit. |
| `DogProfileForm` | `forms/customers.py` | Dog name validation; duplicate check; vet phones NANP-validated. `save()` copies owner info and runs `ensure_feed_credentials(save=False)`. |
| `VaccinationRecordForm` | `forms/customers.py` | `fixed_client` pins the dog; `expires_at >= received_at`; `papers_received` optional checkbox; past expiry warns. |
| `IntakeWizardForm` | `forms/intake.py` | Atomic owner + dog + vet + optional M&G visit creation. |

---

## 7. Google Contacts Import & vCard

**Standing package spec:** [`contacts.md`](https://www.google.com/search?q=contacts.md).

Code lives in `operations/services/contacts/` (`schemas.py`, `parsers.py`, `heuristics.py`, `matching.py`, `importers.py`, `session.py`, `vcard.py`).

---

## 8. Views (`operations/views/customers/`)

Organized as a domain package:

* `clients.py`: `client_list`, `customer_detail`, `dog_detail`, `customer_edit`, `dog_edit`, `customer_add_dog`
* `intake.py`: `client_intake`, `client_create`, `dog_create_customer`
* `vaccinations.py`: `dog_vaccinations`, `add_vaccination`, `validate_vaccination`
* `contacts.py`: `contact_sync`, `contact_import_preview`, `contact_import_selected`, `client_vcard`
* `actions.py`: `dog_hide`, `dog_unhide`, `advance_pipeline`, `update_coi`, `dog_feed_regenerate`

---

## 9. Tests

`CustomerOwnerFormTests`, `AddressHandlingTests`, `CognitiveLoadUXTests`, `DogProfileFormTests`, `IntakeWizardTests`, `ContactDataTests`, `CustomerEditTests`, `CustomerViewsHttpTests`, `ContactSyncTests`, `ComplianceTests`, `VaccinationExpiryViewTests`, `FeedSlugTests`, `CustomerFeedTests` in `operations/tests.py`.

---

## 10. Not Yet Built

* PDF/image upload for vet papers
* Outbound email/SMS alerts before `expires_at`
* Multiple emergency contacts per owner (single fallback today)
* PWA push alerts to `owner_phone` on new timeline photos