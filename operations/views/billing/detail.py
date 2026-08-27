from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from operations.models import AccountStatement
from operations.services.statements import format_statement_email


@login_required
@require_GET
def statement_detail(request, pk):
    """
    Statement detail view with formatted email preview.
    """
    statement = get_object_or_404(
        AccountStatement.objects.select_related('client'),
        pk=pk
    )
    email_body = format_statement_email(statement)
    return render(request, 'operations/statement_detail.html', {
        'statement': statement,
        'email_body': email_body,
    })