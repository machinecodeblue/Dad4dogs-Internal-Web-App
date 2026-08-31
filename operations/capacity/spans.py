from datetime import date, datetime, time, timedelta
from django.utils import timezone


def as_local(dt: datetime) -> datetime:
    """Project-local datetime; naive values are treated as America/Toronto wall time."""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def capacity_span_dates(visit) -> tuple[date, date]:
    """Local calendar days that overlap the visit (scheduled_end__gt=day_start).

    An end exactly at local midnight belongs to the prior day only.
    """
    start_local = as_local(visit.scheduled_start)
    end_local = as_local(visit.scheduled_end)
    start_day = start_local.date()
    end_day = end_local.date()
    if end_local.time() == time.min:
        end_day -= timedelta(days=1)
    if end_day < start_day:
        end_day = start_day
    return start_day, end_day