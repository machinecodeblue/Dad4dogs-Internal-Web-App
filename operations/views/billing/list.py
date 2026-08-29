from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from operations.models import AccountStatement
from operations.services.statements import get_workspace_unbilled_summary


@login_required
@require_GET
def statements_list(request):
    """
    Dense listing of account statements.
    Selects related client for dense list rendering.
    """
    statements = (
        AccountStatement.objects
        .select_related('client')
        .order_by('-week_start', 'client__dog_name')
    )
    unbilled = get_workspace_unbilled_summary()
    return render(request, 'operations/statements.html', {
        'statements': statements,
        'unbilled': unbilled,
    })