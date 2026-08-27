# Decision

- **Status:** superseded
- **Live spec:** none yet (schema not implemented). Successor proposal: LLM/Proposed work/Multi-tenant schema Option B.md
- **What we took:** ideas folded into Option B merged proposal (superseded by Multi-tenant schema Option B.md — anti-god-model ideas folded into the merged proposal)
- **What we left:** do not implement from this file
- **Why:** avoid LLMs coding the early merged-god-Workspace sketch or a split doc set

---

To keep `Workspace` from becoming a monolithic "God Model" (a single object responsible for configuration, tenant security, billing, features, and operational orchestration), you need clear boundaries between what lives on the model versus what lives in domain packages.

---

### 1. The Core Rule: Identity vs. Configuration

A God Model happens when every setting, billing state, toggle, and business rule is added as a new column or method directly on the root model.

Prevent this by applying a strict separation of concerns:

* **`Workspace` owns only Tenant Identity & Boundaries:**
* GUID (`id`)


* `slug` / subdomain identifier


* Core status flags (`is_active`, `subscription_tier`)
* Audit timestamps (`created_at`)


* **Domain 1:1 and 1:N models own operational details:**
* **Business Baseline (`BusinessProfile`):** Display name, phones, addresses, hours.


* **Capacity Constraints (`CapacitySettings` or on `BusinessProfile`):** `standard_capacity`, `insurance_ceiling`.


* **Billing Context (`BillingAccount`):** Stripe/payment processor IDs, currency, invoice schedules.


* **Service Catalog (`BusinessService`):** Custom rates, drop-in offerings, duration triggers.





---

### 2. Keep Domain Logic in Services, Not Model Methods

In Django, God Models frequently emerge when developers stuff workflow logic into model helper methods (e.g., `workspace.calculate_capacity()`, `workspace.generate_statements()`, `workspace.send_booking_email()`).

Maintain your existing structure:

| Action | Where It Must Live | Never Put It On `Workspace` |
| --- | --- | --- |
| **Capacity Auditing** | `operations/services/capacity.py`<br> | `Workspace.check_capacity()` |
| **Statement Compilation** | `operations/services/statements.py`<br> | `Workspace.generate_invoices()` |
| **Email/Calendar Sync** | `operations/services/visit_email.py`, `gmail_send.py`<br> | `Workspace.send_email()` |
| **Media Forwarding** | `operations/services/timeline_media.py`<br> | `Workspace.forward_moment()` |

Models should remain lightweight data schemas with invariant validation (`clean()`). Any orchestration involving multiple models, external APIs, or complex business math belongs in a **Service module**.

---

### 3. Maintain the ~150–200 Line Module Guardrail

Apply the file-size limit strictly to your model definitions:

* Instead of putting all models in a single `operations/models.py`, maintain your domain directory package (`operations/models/`):


* `tenant.py` (`Workspace` only — ~40 lines)


* `business.py` (`BusinessProfile` child model — ~60 lines)


* `customers.py` (`CustomerOwner`, `ClientProfile`, `VaccinationRecord` — ~120 lines)


* `scheduling.py` (`Visit`, `VisitSeries`, `TimelineMediaAsset` — ~150 lines)




* Re-export all models in `operations/models/__init__.py` so external imports (`from operations.models import Workspace, Visit`) remain unified and decoupled.



---

### 4. Code Comparison: God Model vs. Clean Bounded Architecture

```python
# ❌ THE GOD MODEL ANTI-PATTERN
class Workspace(models.Model):
    id = models.UUIDField(primary_key=True)
    # Identity
    name = models.CharField(...)
    slug = models.SlugField(...)
    # Settings & Hours
    business_email = models.EmailField(...)
    hours_of_operation = models.TextField(...)
    main_phone = models.CharField(...)
    emergency_phone = models.CharField(...)
    # Capacity
    standard_capacity = models.IntegerField(...)
    insurance_ceiling = models.IntegerField(...)
    # Billing
    stripe_customer_id = models.CharField(...)
    statement_frequency = models.CharField(...)
    # Monolithic methods
    def check_capacity(self, date): ...
    def calculate_statement(self, start_date): ...
    def send_notification(self, message): ...

```

```python
# ✅ THE DECOUPLED BOUNDED PATTERN

# operations/models/tenant.py
class Workspace(models.Model):
    """Pure Tenant Root: boundary & authentication context."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

# operations/models/business.py
class BusinessProfile(models.Model):
    """Pure Settings Child: presentation & operational baseline."""
    workspace = models.OneToOneField('operations.Workspace', on_delete=models.CASCADE, related_name='profile')
    business_name = models.CharField(max_length=150)
    business_email = models.EmailField(blank=True)
    hours_of_operation = models.TextField(blank=True)
    main_phone = models.CharField(max_length=20, blank=True)
    standard_capacity = models.PositiveIntegerField(default=8)
    insurance_ceiling = models.PositiveIntegerField(default=10)

# operations/services/capacity.py
def assess_workspace_capacity(workspace: Workspace, target_date: date):
    """Pure business logic: queries visits within workspace boundary."""
    ...

```

Keeping `Workspace` as a simple identity anchor and delegating domain-specific data and actions to child models and service modules prevents code bloat.