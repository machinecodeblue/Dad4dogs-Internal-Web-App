from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from operations.models import BusinessService
from operations.services.context_tenant import get_active_workspace


@login_required
@require_GET
def service_list(request):
    """Dense catalog list of commercial offerings for the active workspace."""
    workspace = get_active_workspace()
    services = (
        BusinessService.objects.filter(tenant=workspace)
        .prefetch_related('behavior_rules')
        .order_by('target_category', 'name')
    )
    return render(request, 'operations/services/service_list.html', {
        'services': services,
    })
