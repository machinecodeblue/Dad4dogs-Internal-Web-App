from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from operations.models.business import (
    DEFAULT_INSURANCE_CEILING,
    DEFAULT_STANDARD_CAPACITY,
)

STANDARD_CAPACITY = DEFAULT_STANDARD_CAPACITY
WARNING_THRESHOLD = DEFAULT_STANDARD_CAPACITY + 1
INSURANCE_CEILING = DEFAULT_INSURANCE_CEILING


def capacity_limits() -> tuple[int, int]:
    """Standard daily capacity and insurance ceiling from CapacitySettings, else defaults."""
    from operations.models import CapacitySettings
    from operations.services.context_tenant import (
        ACTIVE_WORKSPACE_SLUG,
        get_active_workspace,
    )

    # Single JOIN query on the hot path (same budget as the old singleton values_list).
    row = (
        CapacitySettings.objects.filter(workspace__slug=ACTIVE_WORKSPACE_SLUG)
        .values_list('standard_capacity', 'insurance_ceiling')
        .first()
    )
    if not row:
        get_active_workspace()
        row = (
            CapacitySettings.objects.filter(workspace__slug=ACTIVE_WORKSPACE_SLUG)
            .values_list('standard_capacity', 'insurance_ceiling')
            .first()
        )
    if not row:
        return STANDARD_CAPACITY, INSURANCE_CEILING
    standard, ceiling = row
    if not standard or standard < 1:
        standard = STANDARD_CAPACITY
    if not ceiling or ceiling < 1:
        ceiling = INSURANCE_CEILING
    if ceiling < standard:
        ceiling = standard
    return standard, ceiling


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
        _overlapping_visits(span_start, span_end, exclude_visit_id)
        .filter(client_id=client_id)
        .select_related('client')
        .first()
    )


def count_dogs_on_day(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> int:
    """Count distinct dogs with an active visit overlapping the given calendar day."""
    day_start, day_end = _day_bounds(day)
    qs = _overlapping_visits(day_start, day_end, exclude_visit_id)
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


def _capacity_status(
    count: int,
    day: date,
    *,
    standard: int | None = None,
    ceiling: int | None = None,
) -> dict:
    if standard is None or ceiling is None:
        standard, ceiling = capacity_limits()
    base = {
        'count': count,
        'standard': standard,
        'ceiling': ceiling,
    }
    if count > ceiling:
        return {
            **base,
            'status': 'blocked',
            'message': (
                f'Insurance ceiling reached: {count} dogs scheduled on {day}. '
                f'Maximum {ceiling} dogs allowed.'
            ),
        }
    if count > standard:
        return {
            **base,
            'status': 'warning',
            'message': (
                f'Capacity warning: {count} dogs on {day}. '
                f'Standard capacity is {standard}; insurance allows up to {ceiling}.'
            ),
        }
    return {
        **base,
        'status': 'ok',
        'message': f'{count} of {standard} standard capacity used on {day}.',
    }


def assess_capacity(
    day: date,
    exclude_visit_id: int | None = None,
    include_client_id: int | None = None,
) -> dict:
    """
    Return capacity status for a calendar day.

    Limits come from Business Settings (defaults: 8 standard, 10 insurance).
    - count <= standard: ok
    - standard < count <= insurance: warning
    - count > insurance: blocked
    """
    standard, ceiling = capacity_limits()
    count = count_dogs_on_day(
        day,
        exclude_visit_id=exclude_visit_id,
        include_client_id=include_client_id,
    )
    return _capacity_status(count, day, standard=standard, ceiling=ceiling)


def _as_local(dt: datetime) -> datetime:
    """Project-local datetime; naive values are treated as America/Toronto wall time."""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _capacity_span_dates(visit) -> tuple[date, date]:
    """Local calendar days that overlap the visit (same rule as scheduled_end__gt=day_start).

    An end exactly at local midnight belongs to the prior day only ΓÇö SQL uses
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

    if include_client_id is not None:
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
    service = getattr(visit, 'business_service', None)
    # Non-dog or capacity-exempt catalog offerings skip facility dog caps.
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

    start_day, end_day = _capacity_span_dates(visit)
    standard, ceiling = capacity_limits()
    counts = _daily_dog_counts(
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
        result = _capacity_status(
            counts.get(day, 0),
            day,
            standard=standard,
            ceiling=ceiling,
        )
        if priority[result['status']] > priority[worst['status']]:
            worst = result
        day += timedelta(days=1)
    return worst
