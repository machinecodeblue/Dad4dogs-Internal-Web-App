from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from operations.models import AccountStatement
from operations.services.statements import format_statement_email


@login_required
def statements_list(request):
    statements = AccountStatement.objects.select_related('client')
    return render(request, 'operations/statements.html', {'statements': statements})


@login_required
def statement_detail(request, pk):
    statement = get_object_or_404(AccountStatement, pk=pk)
    email_body = format_statement_email(statement)
    return render(request, 'operations/statement_detail.html', {
        'statement': statement,
        'email_body': email_body,
    })