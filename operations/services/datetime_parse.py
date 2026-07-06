"""Parse free-text date/time strings (typed or speech-to-text) for visit scheduling."""

from datetime import datetime
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser
from django.utils import timezone

TZ = ZoneInfo('America/Toronto')


def format_datetime_display(dt: datetime) -> str:
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt.replace(tzinfo=TZ)
    hour = local.strftime('%I').lstrip('0') or '12'
    return f'{local.strftime("%b %d, %Y")} {hour}:{local.strftime("%M %p")}'


def format_datetime_input(dt: datetime) -> str:
    """Friendly text pre-filled when editing an existing visit."""
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt.replace(tzinfo=TZ)
    hour = local.strftime('%I').lstrip('0') or '12'
    return f'{local.strftime("%B %d, %Y")} {hour}:{local.strftime("%M %p")}'


def parse_datetime_text(text: str, default: datetime | None = None) -> datetime:
    """
    Parse natural language like "April 11th 2026 5 p.m." into an aware datetime.

    When the text omits a date, `default` supplies missing parts (useful for end times).
    """
    text = (text or '').strip()
    if not text:
        raise ValueError('Enter a date and time.')

    base = default or timezone.localtime(timezone.now())
    if timezone.is_aware(base):
        base = timezone.localtime(base)
    base_naive = base.replace(tzinfo=None, minute=0, second=0, microsecond=0)

    try:
        parsed = date_parser.parse(text, fuzzy=True, default=base_naive)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f'Could not understand "{text}". Try e.g. April 11, 2026 5 pm.') from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    else:
        parsed = parsed.astimezone(TZ)

    return parsed