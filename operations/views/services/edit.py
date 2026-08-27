from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from operations.forms.services import BusinessServiceForm, ServiceBehaviorRuleForm
from operations.models import BusinessService
from operations.services.context_tenant import get_active_workspace
from operations.views.services.helpers import form_error_message


@login_required
@require_http_methods(['GET', 'POST'])
def service_create(request):
    workspace = get_active_workspace()
    form = BusinessServiceForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            service = form.save(commit=False)
            service.tenant = workspace
            service.save()
            messages.success(request, f"Service '{service.name}' created.")
            return redirect('operations:service_edit', pk=service.pk)
        messages.error(request, form_error_message(form))

    return render(request, 'operations/services/service_form.html', {
        'form': form,
        'title': 'New Business Service',
        'service': None,
        'rule_form': None,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def service_edit(request, pk):
    workspace = get_active_workspace()
    service = get_object_or_404(BusinessService, pk=pk, tenant=workspace)
    form = BusinessServiceForm(request.POST or None, instance=service)

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, f"Service '{service.name}' updated.")
            return redirect('operations:service_edit', pk=service.pk)
        messages.error(request, form_error_message(form))

    return render(request, 'operations/services/service_form.html', {
        'form': form,
        'service': service,
        'title': f'Edit {service.name}',
        'rule_form': ServiceBehaviorRuleForm(),
    })
