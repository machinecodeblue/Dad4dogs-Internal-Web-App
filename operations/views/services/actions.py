from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from operations.models import BusinessService
from operations.services.context_tenant import get_active_workspace


@login_required
@require_POST
def service_toggle_active(request, pk):
    """Toggle catalog visibility without deleting history."""
    workspace = get_active_workspace()
    service = get_object_or_404(BusinessService, pk=pk, tenant=workspace)
    service.is_active = not service.is_active
    service.save(update_fields=['is_active', 'updated_at'])
    state = 'activated' if service.is_active else 'deactivated'
    messages.success(request, f"Service '{service.name}' {state}.")
    return redirect('operations:service_list')


@login_required
@require_POST
def service_deactivate(request, pk):
    """Soft-hide: set is_active=False (same outcome as deactivate via toggle)."""
    workspace = get_active_workspace()
    service = get_object_or_404(BusinessService, pk=pk, tenant=workspace)
    if service.is_active:
        service.is_active = False
        service.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f"Service '{service.name}' removed from active offerings.")
    return redirect('operations:service_list')
