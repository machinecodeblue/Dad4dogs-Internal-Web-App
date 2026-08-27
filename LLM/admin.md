# Domain: Admin

**Covers:** baseline Dad4dogs business details — identity, address, hours, phone numbers, daily capacity, and (planned) stable document storage.

**Code packages:** `operations/models/tenant.py` (`Workspace`), `operations/models/business.py` (`BusinessProfile`, `CapacitySettings`), `forms/business.py`, `views/business.py`  
**Bridge:** `operations/services/context_tenant.py` — `get_active_workspace()`  
**Template:** `operations/templates/operations/business_settings.html`

---

## 1. Purpose

David needs a single place to maintain **stable business facts** that rarely change — contact info, hours, **daily capacity**, and eventually certificates and other documents. This is separate from:

- **Customer COI** (`CustomerOwner`) — per-client insurance confirmation
- **Django admin** (`/admin/`) — low-level data editing and auth login

The **Settings** screen (`/settings/`) is the day-to-day admin tool for business baseline data.

---

## 2. Data Model (Option B multi-tenant)

### `Workspace` (tenant root)

Thin identity only: UUID `id`, unique `slug` (e.g. `dad4dogs`), `is_active`, timestamps.  
**No** display name, phones, hours, or capacity on this model. See `applicationphilosophy.md` / Decision *Multi-tenant schema Option B*.

Single-operator today: `get_active_workspace()` ensures slug `dad4dogs` plus profile and capacity rows.

### `BusinessProfile` (OneToOne → Workspace)

Brand / contact baseline. Access via `BusinessProfile.load()` (active workspace).

| Field | Purpose |
|-------|---------|
| `workspace` | OneToOne to `Workspace` |
| `business_name` | Display name (default: `Dad4dogs`) — customer-facing brand |
| `business_email` | Primary business email for client communications |
| `address` | Full mailing or service address (free text) |
| `hours_of_operation` | When clients can reach you or drop off/pick up (free text) |
| `main_phone` | Primary business line |
| `secondary_phone` | Alternate line (e.g. secondary mobile) |
| `emergency_phone` | Number clients call if there is an urgent problem |
| `updated_at` | Last save timestamp |

### `CapacitySettings` (OneToOne → Workspace)

Facility capacity numbers only. Logic stays in `operations/capacity.py`.

| Field | Purpose |
|-------|---------|
| `workspace` | OneToOne to `Workspace` |
| `standard_capacity` | Comfortable daily dog count (default **8**). Days above this warn. |
| `insurance_ceiling` | Hard maximum for new bookings (default **10**). Must be ≥ standard. |
| `updated_at` | Last save timestamp |

Access via `CapacitySettings.load()` or `capacity.capacity_limits()`.

### Rules
1. Use `BusinessProfile.load()` / `CapacitySettings.load()` / `get_active_workspace()` — do not invent a second workspace in app code until multi-tenant auth exists.
2. Do not add per-customer fields here; customer data stays in `customers` domain.
3. Free-text `address` and `hours_of_operation` — mobile-friendly, voice-to-text compatible.
4. When wiring into emails or PDFs, read from `BusinessProfile.load()`; do not hardcode David's details.
5. Daily capacity is **not** a constant in `capacity.py`. Booking, dashboard, and check-in must call `capacity.capacity_limits()` (or use the `standard` / `ceiling` keys on an `assess_capacity` result). Module defaults 8 / 10 only when no usable `CapacitySettings` row.
6. Do not put capacity orchestration methods on `Workspace` or `CapacitySettings`.

### Daily capacity (purpose)

| Setting | Purpose |
|---------|---------|
| **Standard** (`standard_capacity`) | How many dogs David is comfortable having on a normal day. Dashboard occupancy is `count / standard`. Crossing it is a **warning**, not a booking block. |
| **Insurance max** (`insurance_ceiling`) | The policy hard stop. New bookings that would put a day **above** this number are **blocked**. Check-in/out of dogs already on the books is not blocked. |

Insurance max must be ≥ standard (form `clean()` and model `clean()`). Both are 1–50. Change them on `/settings/` — do not ship a new hardcoded 8 or 10.

How it is read at runtime (`operations/capacity.py`):

1. `capacity_limits()` reads `CapacitySettings` for `get_active_workspace()` via `values_list` (no unnecessary `load()` writes on hot paths beyond workspace ensure).
2. Missing row or invalid values fall back to 8 / 10. If insurance < standard in the row, insurance is raised to standard for that check only.
3. `_capacity_status` / `assess_capacity` / `check_visit_capacity` use those two numbers. Dashboard and check-in templates show `{{ capacity.count }} / {{ capacity.standard }}` plus the status message.

**Future** (not Phase 1): weekday staff overrides, isolation buffer, weather modes — see Decision *Capacity setting discussion*. Off-site / non-dog **`capacity_exempt`** belongs on future services catalog (`services.md`).

---

## 3. Screens & URLs

| Screen | URL | Contents |
|--------|-----|----------|
| Business settings | `/settings/` | Identity, location/hours, phones, **standard capacity** + **insurance max** (two models, one form), **Google Contact Sync** (not on `/clients/`) |

Drawer **Settings** links here (not a bottom-nav tab — see `platform.md` §4).

Django admin exposes **Workspace**, **Business profile**, and **Capacity settings**.

---

## 4. Forms

| Form | File | Notes |
|------|------|-------|
| `BusinessProfileForm` | `forms/business.py` | Profile fields + capacity integers bound to `CapacitySettings`. Insurance max cannot be below standard. |

---

## 5. Related

- Multi-tenant schema: Decision `Multi-tenant schema Option B.md`
- Capacity rationale: Decision `Capacity setting discussion.md`
- Visit booking capacity guards: `scheduling.md` §7
