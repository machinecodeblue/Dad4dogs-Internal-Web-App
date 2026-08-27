from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from operations.models import AccountStatement


@login_required
@require_POST
def statement_send_email(request, pk):
    """
    Triggers statement dispatch via Gmail OAuth stack.
    (Hook wired for upcoming email send service).
    """
    statement = get_object_or_404(AccountStatement, pk=pk)
    
    # Placeholder for gmail_send integration
    # Mark status and redirect back to detail view
    messages.info(request, f"Email sending for statement #{statement.pk} is queued.")
    return redirect('statement_detail', pk=statement.pk)