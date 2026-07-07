# Domain: Customers

**Covers:** owners, dogs, COI, vaccinations, emergency contacts, veterinary contacts, Google Contacts import, pipeline per dog.

**Code packages:** `operations/models/customers.py`, `forms/customers.py`, `views/customers.py`  
**Services:** `operations/services/contacts.py`, `feed_slugs.py`, `feed_access.py`  
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

---

## 2. Contact Collection Strategy

Operational contact data is split between **Owner Data** (`CustomerOwner`) and **Dog-Specific Data** (`ClientProfile`).

### 2.1 Primary Owner Contact (`CustomerOwner`)

| Field | Purpose |
|-------|---------|
| `owner_name` | Full name — billing, statements, waivers |
| `owner_salutation` | Pronouns or salutation (optional) |
| `owner_email` | Unique database key — iCal invites, statements, booking email |
| `owner_phone` | **Primary mobile — required on form** — real-time text/PWA alerts |
| `home_address` | Records, liability insurance, emergency home drop-off |

### 2.2 Emergency & Secondary Contact (`CustomerOwner`)

| Field | Purpose |
|-------|---------|
| `emergency_contact_name` | Trusted fallback if primary owner unreachable |
| `emergency_contact_phone` | Direct mobile — tap-to-call on customer/dog detail |
| `emergency_contact_relationship` | Context for logistics (e.g. "Neighbor with house key") |
| `authorized_pickup_names` | Multiline text — one name per line; custody authorization |

Property: `authorized_pickup_list` — parsed non-empty lines for templates.

### 2.3 Medical & Veterinary Contact (`ClientProfile` — per dog)

| Field | Purpose |
|-------|---------|
| `vet_clinic_name` | Primary clinic (e.g. Grey Street Animal Hospital) |
| `vet_name` | Doctor who knows the dog's history |
| `vet_clinic_phone` | Tap-to-call on dog detail and check-in screen |
| `emergency_vet_clinic` | Preferred 24-hour hospital after regular hours |
| `emergency_vet_phone` | Tap-to-call emergency vet |
| `vet_care_authorization` | Dollar cap or directive (e.g. approve $500 triage before contacting owner) |

`VaccinationRecord.vet_clinic` remains for **paper records** per vaccination upload — separate from standing vet contacts on the dog profile.

### Denormalization
`ClientProfile` still copies `owner_name`, `owner_email`, `owner_phone` from `CustomerOwner` on dog save and when customer is edited — supports visit/email queries without joins.

---

## 3. CustomerOwner COI fields

- `coi_sent_at`, `coi_confirmed_received`, `coi_confirmed_at`
- Methods: `mark_coi_sent()`, `mark_coi_received()`, `ensure_for_client()`

---

## 4. ClientProfile pipeline & feed

### Pipeline
`INQUIRY` → `MEET_GREET` → `EVALUATION` → `APPROVED`  
Method: `advance_pipeline()` on dog screen.

### Customer feed fields
- `feed_secret` — speakable unique slug (CV syllables, e.g. `movakitu`)
- `feed_dog_slug` — from dog name (e.g. `lulu`)
- Methods: `ensure_feed_credentials()`, `feed_url()`, `regenerate_feed_secret()`, `sync_feed_dog_slug()`
- Auto-created on first access; included in booking email when `PUBLIC_SITE_URL` is set

### VaccinationRecord
- `expires_at` is **required**
- Current vax = `validated=True` AND `expires_at >= today`
- Method: `mark_validated()`

---

## 5. Screens & URLs

| Screen | URL | Contents |
|--------|-----|----------|
| Client list | `/clients/` | All customers + nested dogs; pipeline filter per dog |
| Add customer | `/clients/add/` | Owner + emergency contacts — no dog |
| Customer | `/customers/<id>/` | Primary contact, emergency/pickup, COI, dog list |
| Edit customer | `/customers/<id>/edit/` | Three-section form: primary, emergency, save |
| Add dog | `/customers/<id>/add-dog/` | Dog profile + vet contacts; pipeline starts at Inquiry |
| Dog | `/dogs/<id>/` | Owner/emergency summary, **vet tap-to-call**, feed, visits |
| Edit dog | `/dogs/<id>/edit/` | Dog profile + veterinary section |
| Regenerate feed | `POST /dogs/<id>/feed/regenerate/` | New `feed_secret` — old links stop working |
| Vaccinations | `/dogs/<id>/vaccinations/` | List, add, validate — dog only |
| Check-in | `/checkin/` | Per-visit owner phone + Vet / Emergency Vet buttons |
| vCard export | `/clients/<id>/vcard/` | Per-dog `.vcf` for Google |
| Contact sync | `/contacts/sync/` | CSV upload hub |
| Import preview | `/contacts/import/` | Analysis before DB write |
| Import confirm | `/contacts/import/add/` | POST selected rows |

### Legacy redirects
- `/clients/<dog_pk>/` → customer view for that dog's owner
- `/clients/<dog_pk>/edit/` → dog edit

### Client list badges
| Badge | Scope |
|-------|-------|
| COI | Customer (`CustomerOwner`) |
| VAX | Dog — current validated non-expired record |
| Pipeline | Dog stage |

---

## 6. Forms

| Form | File | Purpose |
|------|------|---------|
| `CustomerOwnerForm` | `forms/customers.py` | Primary + emergency + pickup contacts; **phone required** |
| `DogProfileForm` | `forms/customers.py` | Dog name, pipeline, **vet contacts**, handling notes |
| `VaccinationRecordForm` | `forms/customers.py` | Per dog; `fixed_client` hides dog selector |

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

### Key service functions (`contacts.py`)
`parse_google_csv`, `analyze_import`, `import_selected_contacts`, `build_vcard`, `is_valid_dog_name`, `assess_name_quality`

---

## 8. Views (customers.py)

`client_list`, `client_create`, `customer_edit`, `customer_detail`, `customer_add_dog`, `dog_edit`, `dog_detail`, `dog_delete`, `dog_feed_regenerate`, `dog_vaccinations`, `update_coi`, `add_vaccination`, `validate_vaccination`, `advance_pipeline`, `contact_sync`, `contact_import_preview`, `contact_import_selected`, `client_vcard`, plus legacy redirects.

Public feed view lives in `views/customer_feed.py` — not in this package.

---

## 9. Tests

`CustomerOwnerFormTests`, `DogProfileFormTests`, `ContactDataTests`, `CustomerEditTests`, `ContactSyncTests`, `ComplianceTests`, `FeedSlugTests`, `CustomerFeedTests` in `operations/tests.py`.

---

## 10. Migrations

| Migration | Contents |
|-----------|----------|
| `0003_owner_coi_and_vax_expiry` | `CustomerOwner` + COI migration |
| `0014_owner_emergency_and_vet_contacts` | Owner emergency/pickup + per-dog vet fields |

---

## 11. Not Yet Built

- PDF/image upload for vet papers
- Expiry reminders before `expires_at`
- Hard block scheduling until compliance + contact completeness
- Live Google People API sync (file-based CSV only today)
- Structured address fields (city/province/postal) — single `home_address` text today
- Multiple emergency contacts per owner (single fallback contact today)
- PWA push to `owner_phone` on new photos (phone field is the hook)