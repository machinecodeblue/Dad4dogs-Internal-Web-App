# Domain: Contacts (service package)

**Part of:** customers domain (owner/dog onboarding & Google sync)  
**Related standing specs:** `customers.md` (models/UI), `phones.py` / `addresses.py` helpers, `platform.md` (Settings hosts Contact Sync)

**Covers:** Google Contacts CSV import (preview → select → write), name/dog heuristics, duplicate matching, vCard export.

**Code packages:**
- `operations/services/contacts/` — business logic package (this file’s focus)
- `operations/views/customers/contacts.py` — thin HTTP: sync, import preview/confirm, vCard

Native onboarding is `/clients/intake/` (`customers.md`). Contacts import is **legacy but maintained** — keep the package small and auditable per `applicationphilosophy.md`.

---

## 0. Package layout

```
operations/services/contacts/
├── __init__.py      # Stable public re-exports
├── schemas.py       # ParsedContact, DuplicateGroup, ImportAnalysis, field constants
├── parsers.py       # parse_google_csv, email/phone splitting, normalize_email
├── heuristics.py    # assess_name_quality, is_valid_dog_name, dog nickname/note extractors
├── matching.py      # Duplicate grouping (CSV vs CSV) and DB matching → analyze_import
├── importers.py     # import_selected_contacts (DB persistence & override resolution)
├── session.py       # analysis_to_session (session serialization)
└── vcard.py         # build_vcard (vCard 3.0)
```

Do **not** re-merge into a monolith `services/contacts.py`. Split further within this package if a file approaches ~150–200 lines.

---

## 1. Public API (`__init__.py`)

| Symbol | Module | Role |
|--------|--------|------|
| `ParsedContact`, `DuplicateGroup`, `ImportAnalysis` | `schemas` | Dataclasses / analysis result shapes |
| `normalize_email` | `parsers` | Lowercase strip |
| `parse_google_csv` | `parsers` | Bytes/CSV → list of `ParsedContact` + skipped |
| `assess_name_quality`, `is_valid_dog_name`, `suggest_client_fields` | `heuristics` | Owner vs dog name quality |
| `analyze_import` | `matching` | Duplicates + DB match + importability |
| `analysis_to_session` | `session` | JSON-serializable dict for Django session |
| `import_selected_contacts` | `importers` | Persist selected rows → `CustomerOwner` / `ClientProfile` |
| `build_vcard` | `vcard` | Per-dog `.vcf` for Google |

Views and forms import **from the package**, not from submodule paths (unless testing internals).

---

## 2. Google CSV import flow

**Never auto-import the full CSV.** Preview first; David selects rows.

1. Export from Google as CSV (`Data samples/google_contacts.csv` = format reference).  
2. Upload at `/contacts/sync/` (`contact_sync`).  
3. `parse_google_csv` → `analyze_import` → `analysis_to_session` → session key **`contact_import_analysis`**.  
4. Preview at `/contacts/import/`: name flags, duplicates, editable owner/dog/phone overrides.  
5. POST `/contacts/import/add/` (`contact_import_selected`) → `import_selected_contacts`.  
   - Always can create/update owner path when `can_import`.  
   - Creates `ClientProfile` only when `is_valid_dog_name()` (never invent a dog from owner first name).

Settings hosts the Google Contact Sync entry (not `/clients/`).

---

## 3. vCard export

- URL: `/clients/<id>/vcard/` → `client_vcard`  
- Uses `build_vcard(client)` with owner address/phone helpers (`addresses`, `phones.e164`).  
- Filenames: keep only `A-Za-z0-9_-`.

---

## 4. Rules for LLMs

1. Preview + checkboxes required — no bulk silent import.  
2. Logic stays in `services/contacts/*`; views stay thin.  
3. Phone **storage/validation** for forms is `phones.py` / `NanpPhoneFormMixin` (`customers.md`); import matching may use `normalize_phone`.  
4. Structured addresses stay in `addresses.py` + `CustomerOwner` fields (`customers.md`) — not this package.  
5. Emergency / vet **contact fields** are customer model/UI (`customers.md`) — not Google import.

---

## 5. Views (`operations/views/customers/contacts.py`)

| Callable | Role |
|----------|------|
| `contact_sync` | Upload hub |
| `contact_import_preview` | Parse + analyze + session |
| `contact_import_selected` | POST selected rows |
| `client_vcard` | Download `.vcf` |

Wrong HTTP verbs → 405. `selected_rows` skip non-integers (no 500).

---

## 6. Tests

`ContactSyncTests`, `NeedsDogNameTests`, and `ContactDataTests` live in `operations/tests/customers/test_contacts.py`. Keep green when touching parsers/matching/importers/vcard.
