# Domain: Customers

**Covers:** owners, dogs, COI, vaccinations, Google Contacts import, pipeline per dog.

**Code packages:** `operations/models/customers.py`, `forms/customers.py`, `views/customers.py`  
**Services:** `operations/services/contacts.py`, `feed_slugs.py`, `feed_access.py`  
**Customer feed & social:** see [`feed.md`](feed.md) — private feed (react, comment, share) and public `/feed/share/<token>/` (re-share, download)

---

## 1. Data Model

| Model | Key | Owns |
|-------|-----|------|
| `CustomerOwner` | `owner_email` (unique) | COI, owner name/phone |
| `ClientProfile` | `owner_email` + `dog_name` (unique) | Pipeline, visits, notes, feed URL credentials |
| `VaccinationRecord` | FK → `ClientProfile` | Vet papers, expiry, validation |
| `FeedAccessLog` | FK → `ClientProfile` | Anonymous feed page views (visitor cookie) |

### Rules
1. A customer may have **zero dogs** until David explicitly adds one.
2. **Pipeline is per dog**, not per customer.
3. **COI is per customer** — all dogs under the same email share COI status.
4. **Vaccinations are per dog** — never on the customer screen.
5. `is_valid_dog_name()` rejects TBD, UNKNOWN, and dog name = owner's first name.

### CustomerOwner COI fields
- `coi_sent_at`, `coi_confirmed_received`, `coi_confirmed_at`
- Methods: `mark_coi_sent()`, `mark_coi_received()`, `ensure_for_client()`

### ClientProfile pipeline
`INQUIRY` → `MEET_GREET` → `EVALUATION` → `APPROVED`  
Method: `advance_pipeline()` on dog screen.

### ClientProfile customer feed fields
- `feed_secret` — speakable unique slug (CV syllables, e.g. `movakitu`)
- `feed_dog_slug` — from dog name (e.g. `lulu`)
- Methods: `ensure_feed_credentials()`, `feed_url()`, `regenerate_feed_secret()`, `sync_feed_dog_slug()`
- Auto-created on first access; included in booking email when `PUBLIC_SITE_URL` is set

### VaccinationRecord
- `expires_at` is **required**
- Current vax = `validated=True` AND `expires_at >= today`
- Method: `mark_validated()`

---

## 2. Screens & URLs

| Screen | URL | Contents |
|--------|-----|----------|
| Client list | `/clients/` | All customers + nested dogs; pipeline filter per dog |
| Add customer | `/clients/add/` | Owner only — no dog |
| Customer | `/customers/<id>/` | COI, dog list, Add Dog — **no vaccinations** |
| Edit customer | `/customers/<id>/edit/` | |
| Add dog | `/customers/<id>/add-dog/` | Pipeline starts at Inquiry |
| Dog | `/dogs/<id>/` | Pipeline, visits, **customer feed link** (copy/regenerate/stats) |
| Edit dog | `/dogs/<id>/edit/` | Syncs `feed_dog_slug` when dog name changes |
| Regenerate feed | `POST /dogs/<id>/feed/regenerate/` | New `feed_secret` — old links stop working |
| Vaccinations | `/dogs/<id>/vaccinations/` | List, add, validate — dog only |
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

## 3. Forms

| Form | File | Purpose |
|------|------|---------|
| `CustomerOwnerForm` | `forms/customers.py` | Add/edit customer |
| `DogProfileForm` | `forms/customers.py` | Add/edit dog; copies owner fields from customer |
| `VaccinationRecordForm` | `forms/customers.py` | Per dog; `fixed_client` hides dog selector |

---

## 4. Google Contacts Import

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

### Export (Dad4dogs → Google)
- Per dog vCard at `/clients/<id>/vcard/`
- Includes `NOTE: Dog: <name>`

### Key service functions (`contacts.py`)
`parse_google_csv`, `analyze_import`, `import_selected_contacts`, `build_vcard`, `is_valid_dog_name`, `assess_name_quality`

---

## 5. Views (customers.py)

`client_list`, `client_create`, `customer_edit`, `customer_detail`, `customer_add_dog`, `dog_edit`, `dog_detail`, `dog_delete`, `dog_feed_regenerate`, `dog_vaccinations`, `update_coi`, `add_vaccination`, `validate_vaccination`, `advance_pipeline`, `contact_sync`, `contact_import_preview`, `contact_import_selected`, `client_vcard`, plus legacy redirects.

Public feed view lives in `views/customer_feed.py` — not in this package.

---

## 6. Tests

`CustomerOwnerFormTests`, `DogProfileFormTests`, `ContactSyncTests`, `ComplianceTests`, `FeedSlugTests`, `CustomerFeedTests` in `operations/tests.py`.

---

## 7. Not Yet Built

- PDF/image upload for vet papers
- Expiry reminders before `expires_at`
- Hard block scheduling until compliance complete
- Live Google People API sync (file-based CSV only today)