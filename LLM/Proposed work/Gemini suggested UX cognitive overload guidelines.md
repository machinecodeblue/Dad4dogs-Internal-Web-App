## UX & Information Architecture: Cognitive Load Constraints

**Adopted** into `LLM/platform.md` (UI Conventions) and the `PROJECT.md` session checklist. This file is the original constraint list — if you change the rules, update `platform.md` and `PROJECT.md` in the same edit.

David operates the app one-handed while actively managing dogs. Avoid "dashboard sprawl" and wall-of-data screens.

### 1. Progressive Disclosure Rules
- **Customer & Dog Detail Screens:** Never show more than 5 primary data points above the fold. 
  - Top Card: Full Name, Tap-to-Call Primary Mobile, Emergency Vet Tap-to-Call.
  - Secondary details (full address, COI timestamps, multiple pickup names, care caps) must be tucked inside collapsible native `<details>` elements or modal drawers.
- **Client List (`/clients/`):**
  - Default view must be a compact list: Dog Name · Owner Name · Status Badge · Primary Phone.
  - Do not render full nested cards with multi-line notes, feed links, and address previews on list views. Use tap-to-expand or link to detail.
  - Group search/filter controls inside a compact toggle if more than 2 filters are present.

### 2. Action Density Rules
- Maximum of **2 primary call-to-action buttons** visible at one time per card (e.g., `Schedule Stay` and `Call Owner`).
- Dangerous or administrative actions (Hide Dog, Regenerate Feed Secret, Reset COI) belong in a grouped "Actions / Admin" drawer at the bottom of the page.

### 3. Visual Noise Reduction
- **Badges:** Show at most 2 badges per card (e.g., Pipeline Stage + Vax Expiry Warning). Do not display OK/Green badges if everything is normal—only highlight actionable states (Expiring, Missing, Blocked).
- **Text Truncation:** Limit notes and free-text fields in lists to a single line with ellipsis (`truncate`).