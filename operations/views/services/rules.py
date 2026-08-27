from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms.services import ServiceBehaviorRuleForm
from operations.models import BusinessService, ServiceBehaviorRule
from operations.services.context_tenant import get_active_workspace
from operations.views.services.helpers import form_error_message


@login_required
@require_http_methods(['GET', 'POST'])
def rule_create(request, service_pk):
    workspace = get_active_workspace()
    service = get_object_or_404(BusinessService, pk=service_pk, tenant=workspace)
    form = ServiceBehaviorRuleForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            rule = form.save(commit=False)
            rule.service = service
            rule.tenant = workspace
            rule.save()
            messages.success(request, f"Rule added to '{service.name}'.")
            return redirect('operations:service_edit', pk=service.pk)
        messages.error(request, form_error_message(form))

    return render(request, 'operations/services/rule_form.html', {
        'form': form,
        'service': service,
    })


@login_required
@require_POST
def rule_delete(request, pk):
    workspace = get_active_workspace()
    rule = get_object_or_404(
        ServiceBehaviorRule.objects.select_related('service'),
        pk=pk,
        tenant=workspace,
    )
    service_pk = rule.service_id
    rule.delete()
    messages.success(request, 'Behavior rule removed.')
    return redirect('operations:service_edit', pk=service_pk)
