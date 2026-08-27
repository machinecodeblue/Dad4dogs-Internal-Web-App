# Decision

- **Status:** superseded
- **Live spec:** none yet (schema not implemented). Successor proposal: LLM/Proposed work/Multi-tenant schema Option B.md
- **What we took:** ideas folded into Option B merged proposal (superseded by Multi-tenant schema Option B.md — original merged-Workspace draft)
- **What we left:** do not implement from this file
- **Why:** avoid LLMs coding the early merged-god-Workspace sketch or a split doc set

---

# Discussion: Foundation-Level Multi-Tenancy Architecture (Django / PostgreSQL)

**Document Focus:** Establishing relational and model-level multi-tenancy at the root schema layer while keeping the single-operator workflow frictionless today.

**Target Compliance:** SOC 2 Security (CC6.1), Confidentiality (CC6.6), and Processing Integrity (CC7.1).

---

## 1. Executive Summary & Philosophy

Retrofitting foreign keys across operational tables after a database is populated causes migration locks, schema fragmentation, and broken unique constraints.

The objective of **Schema-Level Multi-Tenancy** is to introduce a strict tenant root node into Django's relational models now. The user-facing application remains a fast, single-operator tool for daily operations, while the underlying PostgreSQL database enforces structural isolation, compound uniqueness, and tenant-scoped foreign keys from migration zero.

---

## 2. Core Tenancy Model: Retiring the Singleton

The `BusinessProfile` singleton pattern (`singleton_key = 'X'`) is replaced by a first-class `Workspace` (or `Tenant`) model.

```python
# operations/models/tenant.py
import uuid
from django.db import models

class Workspace(models.Model):
    """
    Root multi-tenant entity. Governs business profile, capacity rules,
    billing configurations, and relational isolation boundaries.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Immutable root GUID governing all tenant-scoped entities."
    )
    name = models.CharField(max_length=150, help_text="Business display name (e.g. Dad4dogs)")
    slug = models.SlugField(max_length=100, unique=True, help_text="Unique URL identifier")
    
    # Business Profile / Administrative settings
    business_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    hours_of_operation = models.TextField(blank=True)
    main_phone = models.CharField(max_length=20, blank=True)
    secondary_phone = models.CharField(max_length=20, blank=True)
    emergency_phone = models.CharField(max_length=20, blank=True)
    
    # Daily capacity parameters
    standard_capacity = models.PositiveIntegerField(default=8)
    insurance_ceiling = models.PositiveIntegerField(default=10)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

```

---

## 3. The `TenantAwareModel` Base Pattern

All operational domain models inherit from an abstract base class. This base class standardizes:

1. The `tenant` foreign key.


2. Compound indexes for query efficiency.


3. Relational integrity verification (preventing cross-tenant foreign key bleed).



```python
# operations/models/base.py
from django.core.exceptions import ValidationError
from django.db import models

class TenantAwareModel(models.Model):
    """
    Abstract base guaranteeing tenant partitioning across all domain entities.
    """
    tenant = models.ForeignKey(
        'operations.Workspace',
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        db_index=True,
        help_text="The tenant owning this record."
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        # Verify that any direct related model belongs to the identical tenant
        for field in self._meta.fields:
            if field.is_relation and hasattr(self, field.name):
                related_obj = getattr(self, field.name)
                if related_obj and hasattr(related_obj, 'tenant_id'):
                    if related_obj.tenant_id != self.tenant_id:
                        raise ValidationError(
                            f"Tenant Isolation Violation: {field.name} belongs to tenant "
                            f"{related_obj.tenant_id}, not {self.tenant_id}."
                        )

```

---

## 4. Domain Model Schema Refactoring

### 4.1 Customers Domain (`CustomerOwner`, `ClientProfile`, `VaccinationRecord`)

* **Uniqueness Shift:** Single fields (`owner_email`, `dog_name`) are now scoped per tenant via compound constraints.


* **Integrity:** Two operators can manage a client with the same email without data collision.



```python
# operations/models/customers.py
from django.db import models
from operations.models.base import TenantAwareModel

class CustomerOwner(TenantAwareModel):
    owner_name = models.CharField(max_length=200)
    owner_email = models.EmailField()
    owner_phone = models.CharField(max_length=20)
    
    # COI and Addresses ...
    coi_confirmed_received = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'owner_email'],
                name='unique_tenant_customer_owner_email'
            )
        ]

class ClientProfile(TenantAwareModel):
    owner = models.ForeignKey(CustomerOwner, on_delete=models.CASCADE, related_name='dogs')
    dog_name = models.CharField(max_length=100)
    
    # Public capability tokens (globally unique)
    feed_secret = models.CharField(max_length=64, unique=True, db_index=True)
    feed_dog_slug = models.SlugField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'owner', 'dog_name'],
                name='unique_tenant_owner_dog_name'
            )
        ]

```

### 4.2 Scheduling Domain (`Visit`, `VisitSeries`, `TimelineMediaAsset`)

* **Visit Indexes:** Replace single-column indexes with compound tenant-aware indexes for PostgreSQL query optimization.



```python
# operations/models/scheduling.py
from django.db import models
from operations.models.base import TenantAwareModel

class Visit(TenantAwareModel):
    client = models.ForeignKey('operations.ClientProfile', on_delete=models.CASCADE, related_name='visits')
    status = models.CharField(max_length=20, default='scheduled')
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    calculated_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'status'], name='tenant_visit_status_idx'),
            models.Index(fields=['tenant', 'scheduled_start'], name='tenant_visit_start_idx'),
            models.Index(fields=['tenant', 'scheduled_end'], name='tenant_visit_end_idx'),
        ]

```

---

## 5. File & Media Path Isolation

Upload callable functions partition file paths dynamically by tenant GUID, preventing cross-tenant media directory bleed.

```python
# operations/services/timeline_media.py
def tenant_media_upload_path(instance, filename):
    """
    Partitions assets by tenant UUID:
    media/tenants/<tenant_uuid>/timeline/%Y/%m/%d/<filename>
    """
    tenant_id = str(instance.tenant.id)
    now = instance.captured_at or timezone.now()
    return f"tenants/{tenant_id}/timeline/{now.strftime('%Y/%m/%d')}/{filename}"

```

---

## 6. Single-Operator Runtime Bridge (`context_tenant.py`)

To use this schema immediately without building tenant-switching UI, a lightweight context helper provides the single active workspace.

```python
# operations/services/context_tenant.py
from operations.models.tenant import Workspace

def get_active_workspace() -> Workspace:
    """
    Temporary single-operator bridge.
    Fetches David's primary workspace record without requiring multi-tenant auth UI.
    """
    workspace, _ = Workspace.objects.get_or_create(
        slug='dad4dogs',
        defaults={'name': 'Dad4dogs', 'standard_capacity': 8, 'insurance_ceiling': 10}
    )
    return workspace

```

---

## 7. SOC 2 Audit Verification Checklist

| SOC 2 Criteria | Architecture Requirement | Implementation Validation |
| --- | --- | --- |
| **CC6.1 (Logical Access)** | Strict tenant scoping on queries.

 | QuerySets on `TenantAwareModel` filter by `tenant_id`. Base model `clean()` blocks cross-tenant foreign key linking.

 |
| **CC6.6 (Data Isolation)** | Boundary enforcement in shared databases.

 | Compound database constraints `(tenant, field)` prevent collisions across tenants.

 |
| **CC7.1 (Integrity)** | State transition verification.

 | Transition guards on `Visit` models (`check_in`, `check_out`) remain fully enforced within the tenant boundary.

 |
| **Data Extraction** | Standalone tenant export pipeline.

 | Relational schema allows deterministic queries (`WHERE tenant_id = :id`) to project data into JSON/SQLite exports.

 |