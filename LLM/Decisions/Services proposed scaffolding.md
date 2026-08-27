# Decision

- **Status:** accepted (partial)
- **Live spec:** LLM/services.md (Phase 1 scaffolding)
- **What we took:** views/services package layout; forms/services.py; BusinessService + ServiceBehaviorRule; settings URLs; pricing_engine as parallel stub
- **What we left:** Checkout still on pricing.py; Visit.business_service FK; capacity_exempt wiring; full overnight TIME_WINDOW engine parity
- **Why:** Catalog CRUD first; avoid risky pricing cutover until seeds + UI exist

---

Following the pattern established in `applicationphilosophy.md` and the domain design in `services.md`, here is the modular package scaffolding for the upcoming **Services & Offerings** domain (`operations/views/services/`, `operations/forms/services/`, and `operations/models/services/`).

---

### 1. Package Layout Overview

```
operations/
├── models/
│   └── services.py          # BusinessService & ServiceBehaviorRule (or models/services/ package)
├── forms/
│   └── services.py          # BusinessServiceForm & ServiceBehaviorRuleForm
├── views/
│   └── services/            # Domain view package
│       ├── __init__.py      # Re-exports service catalog views
│       ├── catalog.py       # service_list (dense setting list)
│       ├── edit.py          # service_create, service_edit
│       ├── rules.py         # rule_create, rule_delete (behavior tier modifiers)
│       ├── actions.py       # service_toggle_active, service_delete (soft-hide)
│       └── helpers.py       # Category choices, form error handlers
└── services/
    └── pricing_engine.py    # Evaluates BusinessService + ServiceBehaviorRule at checkout

```

---

### 2. Views Domain Package (`operations/views/services/`)

#### `operations/views/services/__init__.py`

Re-exports public view callables to keep `operations/views/__init__.py` and `urls.py` stable.

```python
from .actions import service_delete, service_toggle_active
from .catalog import service_list
from .edit import service_create, service_edit
from .rules import rule_create, rule_delete

__all__ = [
    'service_list',
    'service_create',
    'service_edit',
    'rule_create',
    'rule_delete',
    'service_toggle_active',
    'service_delete',
]

```

#### `operations/views/services/catalog.py`

Renders the dense `/settings/services/` management table.

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from operations.models import BusinessService


@login_required
@require_GET
def service_list(request):
    """
    Dense catalog list of active and inactive commercial offerings.
    Follows platform list density rules (hairline rows, minimal chrome).
    """
    services = (
        BusinessService.objects
        .prefetch_related('behavior_rules')
        .order_by('target_category', 'name')
    )
    return render(request, 'operations/services/service_list.html', {
        'services': services,
    })

```

#### `operations/views/services/edit.py`

Handles creating and modifying a service definition (`/settings/services/add/`, `/settings/services/<id>/edit/`).

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from operations.forms.services import BusinessServiceForm
from operations.models import BusinessService


@login_required
@require_http_methods(['GET', 'POST'])
def service_create(request):
    """
    Create a new commercial offering (dog boarding, cat check, drop-in).
    """
    form = BusinessServiceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        service = form.save()
        messages.success(request, f"Service '{service.name}' created.")
        return redirect('service_list')

    return render(request, 'operations/services/service_form.html', {
        'form': form,
        'title': 'New Business Service',
    })


@login_required
@require_http_methods(['GET', 'POST'])
def service_edit(request, pk):
    """
    Edit baseline rates, capacity-exempt status, or category.
    """
    service = get_object_or_404(BusinessService, pk=pk)
    form = BusinessServiceForm(request.POST or None, instance=service)
    
    if request.method == 'POST' and form.is_valid():
        service = form.save()
        messages.success(request, f"Service '{service.name}' updated.")
        return redirect('service_list')

    return render(request, 'operations/services/service_form.html', {
        'form': form,
        'service': service,
        'title': f"Edit {service.name}",
    })

```

#### `operations/views/services/rules.py`

Configures conditional duration or time-window pricing modifiers (`ServiceBehaviorRule`).

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms.services import ServiceBehaviorRuleForm
from operations.models import BusinessService, ServiceBehaviorRule


@login_required
@require_http_methods(['GET', 'POST'])
def rule_create(request, service_pk):
    """
    Attach a duration/threshold rule to a parent service.
    """
    service = get_object_or_404(BusinessService, pk=service_pk)
    form = ServiceBehaviorRuleForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        rule = form.save(commit=False)
        rule.service = service
        rule.save()
        messages.success(request, f"Rule added to '{service.name}'.")
        return redirect('service_edit', pk=service.pk)

    return render(request, 'operations/services/rule_form.html', {
        'form': form,
        'service': service,
    })


@login_required
@require_POST
def rule_delete(request, pk):
    """
    Remove a behavior rule modifier.
    """
    rule = get_object_or_404(ServiceBehaviorRule, pk=pk)
    service_pk = rule.service_id
    rule.delete()
    messages.success(request, "Behavior rule removed.")
    return redirect('service_edit', pk=service_pk)

```

#### `operations/views/services/actions.py`

Safe mutations (soft-toggling active visibility and soft-deletion).

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from operations.models import BusinessService


@login_required
@require_POST
def service_toggle_active(request, pk):
    """
    Toggle service availability in booking dropdowns without deleting history.
    """
    service = get_object_or_404(BusinessService, pk=pk)
    service.is_active = not service.is_active
    service.save(update_fields=['is_active'])
    
    state = "activated" if service.is_active else "deactivated"
    messages.success(request, f"Service '{service.name}' {state}.")
    return redirect('service_list')


@login_required
@require_POST
def service_delete(request, pk):
    """
    Soft-delete a service by setting is_active=False.
    """
    service = get_object_or_404(BusinessService, pk=pk)
    service.is_active = False
    service.save(update_fields=['is_active'])
    messages.success(request, f"Service '{service.name}' removed from active offerings.")
    return redirect('service_list')

```

---

### 3. Forms Domain File (`operations/forms/services.py`)

```python
from django import forms
from operations.models import BusinessService, ServiceBehaviorRule


class BusinessServiceForm(forms.ModelForm):
    class Meta:
        model = BusinessService
        fields = [
            'name',
            'slug',
            'target_category',
            'rate_type',
            'base_rate',
            'is_active',
            'capacity_exempt',
        ]


class ServiceBehaviorRuleForm(forms.ModelForm):
    class Meta:
        model = ServiceBehaviorRule
        fields = [
            'trigger_type',
            'threshold_value',
            'modified_rate',
        ]

```

---

### 4. Pricing Evaluation Service (`operations/services/pricing_engine.py`)

Separates calculation logic from views and models:

```python
from decimal import Decimal


def calculate_service_fee(service, duration_hours, start_time, end_time):
    """
    Evaluates BusinessService base rates against ServiceBehaviorRule triggers.
    Returns (Decimal total, list breakdown_lines).
    """
    total = Decimal(str(service.base_rate))
    breakdown = [{'label': f"{service.name} (Base)", 'amount': str(total)}]

    for rule in service.behavior_rules.all():
        if rule.trigger_type == 'DURATION_OVER' and duration_hours > rule.threshold_value:
            total = Decimal(str(rule.modified_rate))
            breakdown.append({
                'label': f"Duration Over {rule.threshold_value}h Modifier",
                'amount': str(total)
            })

    return total, breakdown

```

This keeps every file under ~50 lines, isolates business math inside `operations/services/`, and aligns with the multi-tenant architecture.