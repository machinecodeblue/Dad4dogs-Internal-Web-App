"""Month calendar and daily visit agenda for the dashboard."""

from calendar import monthcalendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from operations.models import Visit

ACTIVE_STATUSES = (
    Visit.Status.SCHEDULED,
    Visit.Status.CHECKED_IN,
    Visit.Status.COMPLETED,
)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def visits_for_day(day: date):
    """Visits overlapping a calendar day, ordered by start time."""
    day_start, day_end = _day_bounds(day)
    return (
        Visit.objects.filter(
            status__in=ACTIVE_STATUSES,
            scheduled_start__lt=day_end,
            scheduled_end__gt=day_start,
        )
        .select_related('client')
        .order_by('scheduled_start')
    )


def visit_counts_between(start_day: date, end_day: date) -> dict[date, int]:
    """Count visits per day across a date range (inclusive)."""
    tz = timezone.get_current_timezone()
    range_start = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    range_end = timezone.make_aware(
        datetime.combine(end_day + timedelta(days=1), time.min), tz,
    )
    visits = Visit.objects.filter(
        status__in=ACTIVE_STATUSES,
        scheduled_start__lt=range_end,
        scheduled_end__gt=range_start,
    ).only('scheduled_start', 'scheduled_end')

    counts: dict[date, int] = {}
    current = start_day
    while current <= end_day:
        counts[current] = 0
        current += timedelta(days=1)

    for visit in visits:
        start = timezone.localtime(visit.scheduled_start).date()
        end = timezone.localtime(visit.scheduled_end).date()
        overlap_start = max(start, start_day)
        overlap_end = min(end, end_day)
        day = overlap_start
        while day <= overlap_end:
            counts[day] = counts.get(day, 0) + 1
            day += timedelta(days=1)

    return counts


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def build_month_calendar(
    year: int,
    month: int,
    selected_date: date,
    today: date,
) -> list[list[dict | None]]:
    """Build week rows for a month grid (Monday-first)."""
    first, last = month_bounds(year, month)
    counts = visit_counts_between(first, last)
    weeks = []

    for week in monthcalendar(year, month):
        days = []
        for day_num in week:
            if day_num == 0:
                days.append(None)
                continue
            day = date(year, month, day_num)
            days.append({
                'date': day,
                'day': day_num,
                'visit_count': counts.get(day, 0),
                'is_today': day == today,
                'is_selected': day == selected_date,
            })
        weeks.append(days)

    return weeks