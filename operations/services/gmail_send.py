import base64
import json
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from operations.services.gmail_paths import gmail_credentials_file, gmail_token_file


GMAIL_SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'
BOOKING_ICS_FILENAME = 'dad4dogs_booking.ics'


class GmailSendError(Exception):
    """Raised when Gmail OAuth send fails or is not configured."""


def _token_path() -> Path:
    return gmail_token_file()


def _credentials_path() -> Path:
    return gmail_credentials_file()


def _load_credentials() -> Credentials:
    token_path = _token_path()
    if not token_path.exists():
        raise GmailSendError(
            f'Gmail token not found at {token_path}. '
            f'Run: python oauth_setup.py (OAuth files live in {settings.GMAIL_OAUTH_DIR})',
        )

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        [GMAIL_SEND_SCOPE],
    )
    creds_path = _credentials_path()
    if creds_path.exists():
        client_data = json.loads(creds_path.read_text(encoding='utf-8'))
        expected_client_id = (
            client_data.get('installed', {}).get('client_id')
            or client_data.get('web', {}).get('client_id')
        )
        token_client_id = (creds.client_id or '').strip()
        if expected_client_id and token_client_id and token_client_id != expected_client_id:
            raise GmailSendError(
                'token.json was created for a different OAuth client. '
                'Delete O-Auth Key/token.json and run: python oauth_setup.py',
            )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding='utf-8')
    if not creds.valid:
        raise GmailSendError(
            'Gmail credentials are invalid or expired. Run: python oauth_setup.py',
        )
    return creds


def _apply_from_header(message) -> None:
    from_email = (getattr(settings, 'GMAIL_SEND_FROM', None) or '').strip()
    if from_email:
        message['from'] = from_email


def build_booking_invite_message(
    subject: str,
    body: str,
    to: str,
    ics_bytes: bytes,
) -> MIMEMultipart:
    """
    Build a MIME message with:
    1. multipart/alternative — plain text + inline text/calendar (method=REQUEST) for Gmail
    2. attached .ics file — fail-safe for clients that need double-click import
    """
    if not ics_bytes:
        raise GmailSendError('Calendar payload is required for booking invites.')

    outer = MIMEMultipart('mixed')
    outer['to'] = to.strip()
    outer['subject'] = subject
    _apply_from_header(outer)

    alternative = MIMEMultipart('alternative')
    alternative.attach(MIMEText(body, 'plain', 'utf-8'))

    calendar_inline = MIMEText(ics_bytes.decode('utf-8'), 'calendar', 'utf-8')
    calendar_inline.replace_header(
        'Content-Type',
        'text/calendar; charset="UTF-8"; method=REQUEST',
    )
    alternative.attach(calendar_inline)
    outer.attach(alternative)

    attachment = MIMEBase('application', 'octet-stream')
    attachment.set_payload(ics_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header(
        'Content-Disposition',
        'attachment',
        filename=BOOKING_ICS_FILENAME,
    )
    attachment.add_header(
        'Content-Type',
        f'text/calendar; charset="UTF-8"; name="{BOOKING_ICS_FILENAME}"',
    )
    outer.attach(attachment)

    return outer


def _send_raw_mime(message) -> dict:
    creds = _load_credentials()
    service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        return service.users().messages().send(
            userId='me',
            body={'raw': raw},
        ).execute()
    except Exception as exc:
        raise GmailSendError(
            f'Gmail API rejected the send ({exc}). '
            'Check token with: python manage.py gmail_auth',
        ) from exc


def send_gmail(subject: str, body: str, to: str) -> dict:
    """Send a plain-text email through the authenticated Gmail account."""
    recipient = (to or '').strip()
    if not recipient:
        raise GmailSendError('Recipient email is required.')

    message = MIMEText(body)
    message['to'] = recipient
    message['subject'] = subject
    _apply_from_header(message)
    return _send_raw_mime(message)


def send_gmail_booking_invite(
    subject: str,
    body: str,
    to: str,
    ics_bytes: bytes,
) -> dict:
    """
    Send booking confirmation with calendar invite layers:
    inline MIME calendar (Gmail banner) + .ics attachment (fail-safe).
    """
    recipient = (to or '').strip()
    if not recipient:
        raise GmailSendError('Recipient email is required.')

    message = build_booking_invite_message(subject, body, recipient, ics_bytes)
    return _send_raw_mime(message)