from django.utils import timezone

from operations.models import AccountStatement
from operations.services.gmail_send import GmailSendError, send_gmail

from .format import format_statement_email, statement_email_subject


class StatementEmailError(Exception):
    """Raised when a statement email cannot be sent."""


def send_statement_email(statement: AccountStatement) -> AccountStatement:
    """
    Email the statement via Gmail OAuth and mark it sent.

    On Gmail failure, raise StatementEmailError and leave the row unchanged.
    """
    to = (statement.client.owner_email or '').strip()
    if not to:
        raise StatementEmailError('This dog has no owner email on file.')

    subject = statement_email_subject(statement)
    body = format_statement_email(statement)
    try:
        send_gmail(subject, body, to=to)
    except GmailSendError as exc:
        raise StatementEmailError(str(exc)) from exc

    statement.send_status = AccountStatement.SendStatus.SENT
    statement.sent_at = timezone.now()
    statement.save(update_fields=['send_status', 'sent_at'])
    return statement
