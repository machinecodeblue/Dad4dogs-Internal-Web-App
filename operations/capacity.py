from datetime import date, datetime, time, timedelta

STANDARD_CAPACITY = 8
WARNING_THRESHOLD = 9
INSURANCE_CEILING = 10


def _day_bounds(day: date, tz):
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def count_dogs_on_day(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> int:
    """Count distinct dogs with an active visit overlapping the given calendar day."""
    from .models import Visit

    tz = datetime.now().astimezone().tzinfo
    day_start, day_end = _day_bounds(day, tz)

    qs = Visit.objects.filter(
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN, Visit.Status.COMPLETED],
        scheduled_start__lt=day_end,
        scheduled_end__gt=day_start,
    )
    if exclude_visit_id:
        qs = qs.exclude(pk=exclude_visit_id)

    client_ids = set(qs.values_list('client_id', flat=True).distinct())
    if include_client_id:
        client_ids.add(include_client_id)
    return len(client_ids)


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


def check_visit_capacity(visit) -> dict:
    """Check capacity for every calendar day the visit spans."""
    tz = visit.scheduled_start.tzinfo
    start_day = visit.scheduled_start.astimezone(tz).date()
    end_day = visit.scheduled_end.astimezone(tz).date()

    worst = {'count': 0, 'status': 'ok', 'message': ''}
    day = start_day
    while day <= end_day:
        result = assess_capacity(
            day,
            exclude_visit_id=visit.pk,
            include_client_id=visit.client_id,
        )
        priority = {'ok': 0, 'warning': 1, 'blocked': 2}
        if priority[result['status']] > priority[worst['status']]:
            worst = result
        day += timedelta(days=1)
    return worst