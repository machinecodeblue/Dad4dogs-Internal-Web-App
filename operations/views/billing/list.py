from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from operations.models import AccountStatement


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
    return render(request, 'operations/statements.html', {
        'statements': statements,
    })