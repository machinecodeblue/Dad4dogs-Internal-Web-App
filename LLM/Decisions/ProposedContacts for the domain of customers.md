# Decision

- **Status:** accepted
- **Live spec:** LLM/contacts.md (package map + API); LLM/customers.md points here for import/vCard
- **What we took:** operations/services/contacts/ modular package layout; stable __init__ re-exports
- **What we left:** Did not fold addresses/phones into contacts/; views remain under iews/customers/contacts.py
- **Why:** Keep Google import/vCard logic auditable and aligned with applicationphilosophy without bloating customers.md

---

# This document is a proposal for the contact services, which is part of the customer's domain. 

##  1. Deployment package 
```
operations/services/contacts/
├── __init__.py          # Stable public re-exports (parse_google_csv, analyze_import, etc.)
├── schemas.py           # ParsedContact, DuplicateGroup, ImportAnalysis, field constants
├── parsers.py           # parse_google_csv, email/phone splitting, email normalization
├── heuristics.py        # assess_name_quality, is_valid_dog_name, dog nickname/note extractors
├── matching.py          # Duplicate grouping (CSV vs CSV) and DB matching
├── importers.py         # import_selected_contacts (DB persistence & override resolution)
├── session.py           # analysis_to_session (session serialization dictionary builder)
└── vcard.py             # build_vcard, _vcard_escape (vCard 3.0 generation)
```