"""Generate recurring visit occurrences (Google Calendar–style repeat)."""

import re
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from .datetime_parse import parse_datetime_text

MAX_OCCURRENCES = 52

FREQUENCY_NONE = 'none'
FREQUENCY_DAILY = 'daily'
FREQUENCY_WEEKLY = 'weekly'
FREQUENCY_WEEKDAYS = 'weekdays'
FREQUENCY_MONTHLY = 'monthly'

FREQUENCY_CHOICES = [
    (FREQUENCY_NONE, 'Does not repeat'),
    (FREQUENCY_DAILY, 'Daily'),
    (FREQUENCY_WEEKLY, 'Weekly'),
    (FREQUENCY_WEEKDAYS, 'Every weekday (Mon–Fri)'),
    (FREQUENCY_MONTHLY, 'Monthly'),
]

END_AFTER = 'after'
END_ON = 'on'

WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def parse_repeat_ends(text: str, anchor_start: datetime) -> tuple[str, int | None, datetime | None]:
    """
    Parse a single "ends" field — number of times or an end date.

    Returns (end_type, count, until_datetime).
    """
    text = (text or '').strip()
    if not text:
        raise ValueError('Enter how many times (e.g. 5) or an end date (e.g. April 15, 2026).')

    if re.fullmatch(r'\d+', text):
        count = int(text)
        if count < 1 or count > MAX_OCCURRENCES:
            raise ValueError(f'Enter a number from 1 to {MAX_OCCURRENCES}.')
        return END_AFTER, count, None

    count_match = re.fullmatch(
        r'(\d+)\s*(?:times?|occurrences?|visits?)\s*',
        text,
        re.IGNORECASE,
    )
    if count_match:
        count = int(count_match.group(1))
        if count < 1 or count > MAX_OCCURRENCES:
            raise ValueError(f'Enter a number from 1 to {MAX_OCCURRENCES}.')
        return END_AFTER, count, None

    try:
        until = parse_datetime_text(text, default=anchor_start)
    except ValueError as exc:
        raise ValueError(
            'Enter a number (e.g. 5) or an end date (e.g. April 15, 2026).',
        ) from exc

    if timezone.localtime(until).date() < timezone.localtime(anchor_start).date():
        raise ValueError('End date must be on or after the first visit.')

    return END_ON, None, until


def weekly_label(start: datetime) -> str:
    local = timezone.localtime(start) if timezone.is_aware(start) else start
    return WEEKDAY_NAMES[local.weekday()]


def generate_repeat_occurrences(
    scheduled_start: datetime,
    scheduled_end: datetime,
    frequency: str,
    interval: int = 1,
    end_type: str = END_AFTER,
    count: int | None = None,
    until: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """
    Return (start, end) pairs for each occurrence in a repeat series.

    Mirrors common Google Calendar patterns: daily, weekly, weekdays, monthly;
    ends after N occurrences or on a date (inclusive of starts on that date).
    """
    if frequency == FREQUENCY_NONE:
        return [(scheduled_start, scheduled_end)]

    duration = scheduled_end - scheduled_start
    interval = max(1, interval)
    target_count = count if end_type == END_AFTER else MAX_OCCURRENCES
    if end_type == END_AFTER:
        target_count = min(max(1, count or 1), MAX_OCCURRENCES)
    until_date = timezone.localtime(until).date() if until else None

    occurrences: list[tuple[datetime, datetime]] = []

    if frequency == FREQUENCY_WEEKDAYS:
        current = scheduled_start
        steps = 0
        while len(occurrences) < target_count and steps < 366:
            local = timezone.localtime(current)
            if local.weekday() < 5:
                if until_date and local.date() > until_date:
                    break
                occurrences.append((current, current + duration))
                if end_type == END_AFTER and len(occurrences) >= target_count:
                    break
            current += timedelta(days=1)
            steps += 1
        return occurrences

    index = 0
    while len(occurrences) < MAX_OCCURRENCES:
        if frequency == FREQUENCY_DAILY:
            occ_start = scheduled_start + timedelta(days=index * interval)
        elif frequency == FREQUENCY_WEEKLY:
            occ_start = scheduled_start + timedelta(weeks=index * interval)
        elif frequency == FREQUENCY_MONTHLY:
            occ_start = scheduled_start + relativedelta(months=index * interval)
        else:
            break

        local = timezone.localtime(occ_start)
        if until_date and local.date() > until_date:
            break

        occurrences.append((occ_start, occ_start + duration))

        if end_type == END_AFTER and len(occurrences) >= target_count:
            break

        index += 1

    return occurrences


def repeat_summary(
    occurrences: list[tuple[datetime, datetime]],
    frequency: str,
    interval: int,
) -> str:
    if not occurrences or frequency == FREQUENCY_NONE:
        return ''
    from operations.services.datetime_parse import format_datetime_display

    n = len(occurrences)
    first = format_datetime_display(occurrences[0][0])
    if n == 1:
        return first
    last = format_datetime_display(occurrences[-1][0])
    unit = {
        FREQUENCY_DAILY: 'day' if interval == 1 else f'{interval} days',
        FREQUENCY_WEEKLY: 'week' if interval == 1 else f'{interval} weeks',
        FREQUENCY_WEEKDAYS: 'weekday',
        FREQUENCY_MONTHLY: 'month' if interval == 1 else f'{interval} months',
    }.get(frequency, 'visit')
    return f'{n} visits ({unit}) — {first} through {last}'