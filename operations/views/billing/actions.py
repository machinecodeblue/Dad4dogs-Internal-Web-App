from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from operations.models import AccountStatement
from operations.services.statements import StatementEmailError, send_statement_email


@login_required
@require_POST
def statement_send_email(request, pk):
    """Send statement via Gmail; leave row unchanged on OAuth/send failure."""
    statement = get_object_or_404(
        AccountStatement.objects.select_related('client'),
        pk=pk,
    )
    try:
        send_statement_email(statement)
    except StatementEmailError as exc:
        messages.warning(request, str(exc))
        return redirect('operations:statement_detail', pk=statement.pk)

    messages.success(
        request,
        f'Statement emailed to {statement.client.owner_email}.',
    )
    return redirect('operations:statement_detail', pk=statement.pk)
