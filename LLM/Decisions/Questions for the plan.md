# Decision

- **Status:** accepted (resolutions recorded)
- **Live spec:** same as Multi-tenant schema Option B decision
- **What we took:** CapacitySettings split; display name on BusinessProfile; is_active only; merged proposal process
- **What we left:** n/a
- **Why:** Planning Q&A archive

---

# Questions for the plan — resolutions

Companion notes from planning. **Authoritative design:** `Multi-tenant schema Option B.md`.

| # | Topic | Gemini-style recommendation in draft | **Locked decision** |
|---|--------|--------------------------------------|---------------------|
| 1 | Capacity location | Keep on `BusinessProfile` (only two ints) | **`CapacitySettings` 1:1 split now** — expect capacity rules to expand; do not lock integers onto the profile |
| 2 | Display name | `slug` on Workspace; name on `BusinessProfile` | **Same — accepted** |
| 3 | Soft deactivate | `is_active` on Workspace for v1 | **Same — accepted** |
| 4 | Django admin hazard | Document / constrain ModelAdmin FK querysets | **Same — accepted** (document in proposal; harden in Phase 2) |

Do not reopen Q1 toward “keep on profile” without David explicitly changing course.
