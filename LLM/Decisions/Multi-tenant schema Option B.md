# Decision

- **Status:** accepted
- **Live spec:** LLM/PROJECT.md (tenancy layout + status); LLM/admin.md (BusinessProfile + CapacitySettings); LLM/platform.md (single-operator bridge); pplicationphilosophy.md (no god Workspace)
- **What we took:** Thin Workspace; BusinessProfile + CapacitySettings 1:1; TenantAwareModel; compound uniques; get_active_workspace(); Phase 1 = two capacity integers only
- **What we left:** QuerySet middleware; membership/auth; owner FK; portable export; weekday capacity overrides
- **Why:** Plant tenant boundaries in Postgres before services/pricing build; keep single-operator UX

---

# Proposed: Multi-Tenant Data Schema (Option B)

**Status:** Accepted — standing schema design; Phase 1 implementation in progress / landed in code  
**Supersedes:** `Multi-tenanted data schema proposal.md`, `Avoiding the God Model with Option B.md`  
**Aligns with:** `applicationphilosophy.md`, `PROJECT.md` Rule C / §9.1, `billing.md` §8  
**Prerequisite for:** configurable services/pricing build (`services.md`)

---

## 1. Goal

Introduce **schema-level multi-tenancy** on PostgreSQL **now**, while the product remains a **single-operator** Dad4dogs tool.

Retrofitting `tenant` foreign keys after the database is full of features causes migration pain and broken uniques. We plant the tenant root and compound constraints before the next major domain (services/pricing).

**Not in this proposal:** tenant switcher UI, login membership, default QuerySet middleware, portable SQLite export code, or `ClientProfile → CustomerOwner` FK refactor.

---

## 2. Locked decisions

| Topic | Decision |
|-------|----------|
| Tenant root | Thin **`Workspace`** (identity/boundary only) |
| Settings | **`BusinessProfile`** OneToOne — brand/contact/hours |
| Capacity | **`CapacitySettings`** OneToOne — standard + insurance ceiling (**must** stay split; expect capacity rules to expand over time — do not fold back onto `BusinessProfile`) |
| Display name | Only on **`BusinessProfile.business_name`**; Workspace uses **`slug`** |
| Lifecycle v1 | **`is_active`** only |
| Owner FK | **Deferred** — keep email / `customer_owner` property |
| Runtime | **`get_active_workspace()`** bridge (slug `dad4dogs`) |
| God model | No fattening Workspace; logic stays in `operations/services/` / `capacity.py` |

---

## 3. Core rule: identity vs configuration

A god model appears when every setting, billing toggle, and workflow method lands on the root tenant row.

| Layer | Owns | Must not own |
|-------|------|----------------|
| **`Workspace`** | UUID, slug, `is_active`, timestamps (optional future `subscription_tier`) | Phones, hours, capacity, Stripe IDs, service rates, `check_capacity()`, email send |
| **`BusinessProfile`** | Display name, email, address, hours, phones | Capacity math, statements, media |
| **`CapacitySettings`** | `standard_capacity`, `insurance_ceiling` | Contact fields, visits |
| **Future `BillingAccount` / `BusinessService`** | Their domains | Anything on Workspace |
| **Services modules** | Capacity assess, statements, Gmail, timeline | Methods on Workspace |

File shape (per `applicationphilosophy.md`):

- `operations/models/tenant.py` — `Workspace` only  
- `operations/models/base.py` — `TenantAwareModel`  
- `operations/models/business.py` — `BusinessProfile` + `CapacitySettings` (split capacity to its own tiny module only if the file grows)  
- Domain packages unchanged in spirit: `customers.py`, `scheduling.py`, `billing.py`  
- `operations/services/context_tenant.py` — `get_active_workspace()`  
- Re-export via `models/__init__.py`

---

## 4. Model sketches

### 4.1 Workspace

```python
# operations/models/tenant.py
class Workspace(models.Model):
    """Pure tenant root: boundary & identity — not a settings bag."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 4.2 BusinessProfile (1:1)

Replace `singleton_key='X'` with:

```python
workspace = models.OneToOneField(
    'operations.Workspace',
    on_delete=models.CASCADE,
    related_name='profile',
)
# business_name, business_email, address, hours, phones — as today
# NO standard_capacity / insurance_ceiling here after split
```

Compatibility: `BusinessProfile.load()` resolves profile for `get_active_workspace()`.

### 4.3 CapacitySettings (1:1)

**Confirmed** (see Decision archive of *Capacity setting discussion* + capacity plan): separate table is required; capacity will grow beyond two integers over time, but **Phase 1 only ships the two existing numbers**.

```python
workspace = models.OneToOneField(
    'operations.Workspace',
    on_delete=models.CASCADE,
    related_name='capacity_settings',
)
standard_capacity = ...  # defaults 8 — warn threshold / dashboard denominator
insurance_ceiling = ...  # defaults 10 — hard booking block; must be >= standard
```

**Semantics (unchanged from today):** standard = comfortable count (warning only); insurance = policy hard stop (blocks new bookings over ceiling; does not block check-in/out).

**Logic:** stays in `operations/capacity.py` — not methods on `CapacitySettings` or `Workspace`.

**Compatibility:** `capacity_limits()` reads active workspace’s `CapacitySettings` (not `singleton_key` filter).

`/settings/` may remain **one screen** editing profile + capacity — two models, one UX.

**Phase 1 does not add:** weekday override maps, isolation buffer columns, weather modes, temperament weights. Those stay future (discussion rationale). Off-site / non-dog **`capacity_exempt`** belongs on future `BusinessService` (`services.md`), not on this table.

### 4.4 TenantAwareModel

```python
class TenantAwareModel(models.Model):
    tenant = models.ForeignKey(
        'operations.Workspace',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        db_index=True,
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        # Reject direct FK relations that point at another tenant's row
        ...
```

Notes:

- Field name `tenant` (SOC 2 language); docs may say workspace.  
- `clean()` is required but **not enough** — creates must set `tenant_id`; **Phase 2** adds default QuerySet filtering.  
- Prefer an explicit `tenant` on child rows (e.g. vaccinations, reactions) for export (`WHERE tenant_id = :id`) even when reachable via parent.

---

## 5. Tenant-aware model checklist

| Model | Action |
|-------|--------|
| `Workspace` | New root (not tenant-aware) |
| `BusinessProfile` | OneToOne `workspace`; drop singleton |
| `CapacitySettings` | New OneToOne |
| `CustomerOwner` | + `tenant`; unique `(tenant, owner_email)` |
| `ClientProfile` | + `tenant`; unique `(tenant, owner_email, dog_name)` |
| `VaccinationRecord` | + `tenant` |
| `FeedAccessLog` | + `tenant` |
| `Visit` / `VisitSeries` | + `tenant`; indexes `(tenant, status|scheduled_*)` |
| `TimelineMediaAsset` / `VisitTimelineEvent` | + `tenant` |
| `MediaReaction` / `MediaComment` | + `tenant` |
| `SharedMediaLink` | + `tenant`; **token stays globally unique** |
| `PendingCalendarEvent` | + `tenant`; revisit `event_uid` uniqueness (prefer per-tenant or keep global if externally unique) |
| `AccountStatement` | + `tenant`; keep `(client, week_start)` |

**Stay globally unique (capability / unguessable):** `feed_secret`, share tokens.

**Deferred:** `ClientProfile.owner` FK to `CustomerOwner`.

**Auth:** no `User`↔`Workspace` yet; future `WorkspaceMembership`.

**Future `BusinessService`:** must include `tenant` from day one.

---

## 6. Media paths

New uploads:

`tenants/<workspace_uuid>/timeline/%Y/%m/%d/<filename>`

Existing on-disk `media/` paths may remain until a follow-up move; do not break live files in the schema migration.

---

## 7. Single-operator bridge

```python
# operations/services/context_tenant.py
def get_active_workspace() -> Workspace:
    workspace, _ = Workspace.objects.get_or_create(
        slug='dad4dogs',
        defaults={'is_active': True},
    )
    # ensure profile + capacity_settings rows exist
    return workspace
```

No tenant switcher UI in this phase.

---

## 8. Phased delivery (honest SOC 2 mapping)

### Phase 1 — Schema foundation (this proposal’s implementation)

- Migrations + backfill for single Dad4dogs workspace  
- Compound uniques / tenant FKs  
- `TenantAwareModel.clean()` cross-tenant checks  
- Bridge + shims for settings/capacity  
- Tenant media `upload_to` for **new** files  
- Tests: two-workspace unique collision; cross-tenant `clean()` failure; single-workspace happy path  

### Phase 2 — Query enforcement (separate proposal/PR)

- Default managers / middleware so unscoped iteration is hard  
- Hardens CC6.1 beyond “developers remember to filter”  

### Later

- `WorkspaceMembership` + auth  
- Portable SQLite export (`billing.md` §8) via `WHERE tenant_id = …`  
- Owner FK refactor  
- Services/pricing catalog (tenant-aware from birth)

| SOC 2 theme | Phase 1 | Phase 2+ |
|-------------|---------|----------|
| Compound isolation / uniques | Yes | — |
| Cross-tenant FK clean() | Yes | — |
| Default query scoping | No | Yes |
| User access to workspace | No | Membership |
| Deterministic tenant extract | Schema ready | Export pipeline |

---

## 9. Implementation order (when David says go)

1. Add `Workspace`, `TenantAwareModel`, `CapacitySettings`; migrate `BusinessProfile` off singleton.  
2. Seed `dad4dogs` + profile + capacity from current singleton row.  
3. Add nullable `tenant`, backfill, then non-null + constraint rewrites.  
4. Wire create paths to set `tenant=get_active_workspace()`.  
5. Update docs: `admin.md`, `platform.md`, `PROJECT.md` status; Decision-archive this proposal.  
6. Do **not** start `services.md` implementation until Phase 1 tenant columns exist.

---

## 10. Admin / hazard note

Even with one workspace, document that Django admin must not casually assign FKs across workspaces once a second tenant exists. Prefer limiting admin inlines / raw_id to tenant-scoped querysets in Phase 2.

---

## 11. Out of scope

- Coding until this proposal is accepted and scheduled  
- Multi-tenant UI  
- Merging capacity/contact back onto Workspace  
- Implementing portable export or services catalog in the same change set as Phase 1 schema  
