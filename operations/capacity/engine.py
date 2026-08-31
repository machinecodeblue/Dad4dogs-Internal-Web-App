from datetime import date, timedelta
from django.db.models import Count, Q

from .limits import capacity_limits, format_capacity_status
from .spans import as_local, capacity_span_dates, day_bounds


def overlapping_visits(
    span_start,
    span_end,
    exclude_visit_id: int | None = None,
    *,
    for_facility_capacity: bool = False,
):
    from operations.models.scheduling.visits import Visit

    qs = Visit.objects.filter(
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN, Visit.Status.COMPLETED],
        scheduled_start__lt=span_end,
        scheduled_end__gt=span_start,
    )
    if exclude_visit_id:
        qs = qs.exclude(pk=exclude_visit_id)
    if for_facility_capacity:
        qs = qs.exclude(business_service__capacity_exempt=True)
    return qs


def overlapping_dog_visit(
    client_id: int,
    span_start,
    span_end,
    exclude_visit_id: int | None = None,
):
    """Another stay for the same dog whose window overlaps this one, or None."""
    if not client_id:
        return None
    return (
        overlapping_visits(span_start, span_end, exclude_visit_id)
        .filter(client_id=client_id)
        .select_related('client')
        .first()
    )


def count_dogs_on_day(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> int:
    """Count distinct dogs occupying facility capacity on a calendar day."""
    day_start, day_end = day_bounds(day)
    qs = overlapping_visits(
        day_start, day_end, exclude_visit_id, for_facility_capacity=True,
    )
    if include_client_id is not None:
        agg = qs.aggregate(
            total=Count('client_id', distinct=True),
            already=Count('pk', filter=Q(client_id=include_client_id)),
        )
        total = agg['total'] or 0
        if not agg['already']:
            total += 1
        return total
    return qs.aggregate(total=Count('client_id', distinct=True))['total'] or 0


def assess_capacity(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> dict:
    """Return capacity status for a single calendar day."""
    standard, ceiling = capacity_limits()
    count = count_dogs_on_day(
        day,
        exclude_visit_id=exclude_visit_id,
        include_client_id=include_client_id,
    )
    return format_capacity_status(count, day, standard=standard, ceiling=ceiling)


def daily_dog_counts(
    start_day: date,
    end_day: date,
    *,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> dict[date, int]:
    """One query for the span; distinct dogs per local day in memory."""
    span_start, _ = day_bounds(start_day)
    _, span_end = day_bounds(end_day)
    day_windows = []
    day = start_day
    dogs_by_day: dict[date, set[int]] = {}
    while day <= end_day:
        dogs_by_day[day] = set()
        day_windows.append((day, *day_bounds(day)))
        day += timedelta(days=1)

    if include_client_id is not None:
        for client_ids in dogs_by_day.values():
            client_ids.add(include_client_id)

    others = overlapping_visits(
        span_start, span_end, exclude_visit_id, for_facility_capacity=True,
    ).only('client_id', 'scheduled_start', 'scheduled_end')

    for other in others:
        start = as_local(other.scheduled_start)
        end = as_local(other.scheduled_end)
        for d, d_start, d_end in day_windows:
            if start < d_end and end > d_start:
                dogs_by_day[d].add(other.client_id)

    return {d: len(ids) for d, ids in dogs_by_day.items()}


def check_visit_capacity(visit) -> dict:
    """Check capacity for every calendar day the visit spans."""
    service = getattr(visit, 'business_service', None)
    if service is not None and (
        bool(service.capacity_exempt) or service.target_category != 'DOG'
    ):
        standard, ceiling = capacity_limits()
        return {
            'count': 0,
            'standard': standard,
            'ceiling': ceiling,
            'status': 'ok',
            'message': '',
        }

    start_day, end_day = capacity_span_dates(visit)
    standard, ceiling = capacity_limits()
    counts = daily_dog_counts(
        start_day,
        end_day,
        exclude_visit_id=visit.pk,
        include_client_id=visit.client_id,
    )
    worst = {
        'count': 0,
        'standard': standard,
        'ceiling': ceiling,
        'status': 'ok',
        'message': '',
    }
    priority = {'ok': 0, 'warning': 1, 'blocked': 2}
    day = start_day
    while day <= end_day:
        result = format_capacity_status(
            counts.get(day, 0),
            day,
            standard=standard,
            ceiling=ceiling,
        )
        if priority[result['status']] > priority[worst['status']]:
            worst = result
        day += timedelta(days=1)
    return worst