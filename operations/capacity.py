from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

STANDARD_CAPACITY = 8
WARNING_THRESHOLD = 9
INSURANCE_CEILING = 10


def _day_bounds(day: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def _overlapping_visits(span_start, span_end, exclude_visit_id: int | None = None):
    from .models import Visit

    qs = Visit.objects.filter(
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN, Visit.Status.COMPLETED],
        scheduled_start__lt=span_end,
        scheduled_end__gt=span_start,
    )
    if exclude_visit_id:
        qs = qs.exclude(pk=exclude_visit_id)
    return qs


def count_dogs_on_day(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> int:
    """Count distinct dogs with an active visit overlapping the given calendar day."""
    day_start, day_end = _day_bounds(day)
    qs = _overlapping_visits(day_start, day_end, exclude_visit_id)
    if include_client_id:
        agg = qs.aggregate(
            total=Count('client_id', distinct=True),
            already=Count('pk', filter=Q(client_id=include_client_id)),
        )
        total = agg['total'] or 0
        if not agg['already']:
            total += 1
        return total
    return qs.aggregate(total=Count('client_id', distinct=True))['total'] or 0


def _capacity_status(count: int, day: date) -> dict:
    if count > INSURANCE_CEILING:
        return {
            'count': count,
            'status': 'blocked',
            'message': (
                f'Insurance ceiling reached: {count} dogs scheduled on {day}. '
                f'Maximum {INSURANCE_CEILING} dogs allowed.'
            ),
        }
    if count >= WARNING_THRESHOLD:
        return {
            'count': count,
            'status': 'warning',
            'message': (
                f'Capacity warning: {count} dogs on {day}. '
                f'Standard capacity is {STANDARD_CAPACITY}; insurance allows up to {INSURANCE_CEILING}.'
            ),
        }
    return {
        'count': count,
        'status': 'ok',
        'message': f'{count} of {STANDARD_CAPACITY} standard capacity used on {day}.',
    }


def assess_capacity(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> dict:
    """
    Return capacity status for a calendar day.

    - 8 or fewer: ok
    - 9–10: warning (insurance guard)
    - >10: blocked
    """
    count = count_dogs_on_day(
        day,
        exclude_visit_id=exclude_visit_id,
        include_client_id=include_client_id,
    )
    return _capacity_status(count, day)


def _as_local(dt: datetime) -> datetime:
    """Project-local datetime; naive values are treated as America/Toronto wall time."""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _capacity_span_dates(visit) -> tuple[date, date]:
    """Local calendar days that overlap the visit (same rule as scheduled_end__gt=day_start).

    An end exactly at local midnight belongs to the prior day only — SQL uses
    scheduled_end > day_start, so 2026-04-12 00:00 does not occupy 12 April.
    """
    start_local = _as_local(visit.scheduled_start)
    end_local = _as_local(visit.scheduled_end)
    start_day = start_local.date()
    end_day = end_local.date()
    if end_local.time() == time.min:
        end_day -= timedelta(days=1)
    if end_day < start_day:
        end_day = start_day
    return start_day, end_day


def _daily_dog_counts(
    start_day: date,
    end_day: date,
    *,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> dict[date, int]:
    """One query for the whole span; distinct dogs per local day in memory."""
    span_start, _ = _day_bounds(start_day)
    _, span_end = _day_bounds(end_day)
    day_windows = []
    day = start_day
    dogs_by_day: dict[date, set[int]] = {}
    while day <= end_day:
        dogs_by_day[day] = set()
        day_windows.append((day, *_day_bounds(day)))
        day += timedelta(days=1)

    if include_client_id:
        for client_ids in dogs_by_day.values():
            client_ids.add(include_client_id)

    others = _overlapping_visits(
        span_start, span_end, exclude_visit_id,
    ).only('client_id', 'scheduled_start', 'scheduled_end')

    for other in others:
        start = _as_local(other.scheduled_start)
        end = _as_local(other.scheduled_end)
        for day, day_start, day_end in day_windows:
            if start < day_end and end > day_start:
                dogs_by_day[day].add(other.client_id)

    return {day: len(ids) for day, ids in dogs_by_day.items()}


def check_visit_capacity(visit) -> dict:
    """Check capacity for every calendar day the visit spans."""
    start_day, end_day = _capacity_span_dates(visit)
    counts = _daily_dog_counts(
        start_day,
        end_day,
        exclude_visit_id=visit.pk,
        include_client_id=visit.client_id,
    )
    worst = {'count': 0, 'status': 'ok', 'message': ''}
    priority = {'ok': 0, 'warning': 1, 'blocked': 2}
    day = start_day
    while day <= end_day:
        result = _capacity_status(counts.get(day, 0), day)
        if priority[result['status']] > priority[worst['status']]:
            worst = result
        day += timedelta(days=1)
    return worst