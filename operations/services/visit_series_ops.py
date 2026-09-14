"""Bulk shift / cancel for still-scheduled members of a VisitSeries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.models import Visit
from operations.services import visit_calendar
from operations.services.visit_email import VisitEmailError


@dataclass
class SeriesOpResult:
    updated: list[Visit]
    unchanged_other_statuses: int
    calendar_notices: int
    calendar_errors: list[str]
    hard_deleted: int = 0


def scheduled_series_visits(anchor: Visit):
    """Still-scheduled visits in the same series (including anchor), ordered."""
    if not anchor.series_id:
        return Visit.objects.none()
    return (
        Visit.objects.filter(
            series_id=anchor.series_id,
            status=Visit.Status.SCHEDULED,
        )
        .select_related('client', 'business_service')
        .order_by('scheduled_start')
    )


def series_has_scheduled_siblings(anchor: Visit) -> bool:
    if not anchor.series_id:
        return False
    return scheduled_series_visits(anchor).count() > 1


def _proposed_windows(
    visits: list[Visit],
    *,
    anchor: Visit,
    prior_start: datetime,
    prior_end: datetime,
    new_start: datetime,
    new_end: datetime,
) -> list[tuple[Visit, datetime, datetime]]:
    old_duration = prior_end - prior_start
    new_duration = new_end - new_start
    delta_start = new_start - prior_start
    duration_changed = new_duration != old_duration
    proposed = []
    for visit in visits:
        start = visit.scheduled_start + delta_start
        if duration_changed:
            end = start + new_duration
        else:
            end = visit.scheduled_end + delta_start
        proposed.append((visit, start, end))
    return proposed


def _validate_proposed(
    proposed: list[tuple[Visit, datetime, datetime]],
    *,
    business_service,
) -> None:
    exclude_ids = {v.pk for v, _s, _e in proposed}
    for visit, start, end in proposed:
        if end <= start:
            raise ValidationError('End must be after start for every visit in the series.')
        clash = (
            Visit.objects.filter(client_id=visit.client_id)
            .exclude(status=Visit.Status.CANCELLED)
            .exclude(pk__in=exclude_ids)
            .filter(scheduled_start__lt=end, scheduled_end__gt=start)
            .select_related('client')
            .first()
        )
        if clash is not None:
            raise ValidationError(
                f'{clash.client.dog_name} is already booked {clash.schedule_display} '
                f'(blocks series move).'
            )
        probe = Visit(
            pk=visit.pk,
            client_id=visit.client_id,
            tenant_id=visit.tenant_id,
            business_service=business_service or visit.business_service,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.SCHEDULED,
        )
        capacity = check_visit_capacity(probe)
        if capacity['status'] == 'blocked':
            raise ValidationError(
                f'{capacity["message"]} (blocks series move for '
                f'{start:%b %d %Y}).'
            )


@transaction.atomic
def shift_scheduled_series(
    anchor: Visit,
    *,
    prior_start: datetime,
    prior_end: datetime,
    new_start: datetime,
    new_end: datetime,
    notes: str | None = None,
    business_service=None,
    immediate_calendar: bool = False,
    request=None,
) -> SeriesOpResult:
    """
    Shift all still-scheduled visits in anchor.series by the same delta as
    prior_start/end → new_start/end. All-or-nothing.
    """
    if not anchor.series_id:
        raise ValidationError('This visit is not part of a repeat series.')

    visits = list(scheduled_series_visits(anchor))
    if not visits:
        raise ValidationError('No scheduled visits left in this series.')

    unchanged = (
        Visit.objects.filter(series_id=anchor.series_id)
        .exclude(status=Visit.Status.SCHEDULED)
        .count()
    )
    proposed = _proposed_windows(
        visits,
        anchor=anchor,
        prior_start=prior_start,
        prior_end=prior_end,
        new_start=new_start,
        new_end=new_end,
    )
    _validate_proposed(proposed, business_service=business_service)

    # Save far-side first so mid-shift windows do not clash with not-yet-moved siblings.
    delta_seconds = (new_start - prior_start).total_seconds()
    save_order = list(reversed(proposed)) if delta_seconds > 0 else proposed

    updated_by_id: dict[int, Visit] = {}
    for visit, start, end in save_order:
        visit.scheduled_start = start
        visit.scheduled_end = end
        update_fields = ['scheduled_start', 'scheduled_end', 'updated_at']
        if notes is not None and visit.pk == anchor.pk:
            visit.notes = notes
            update_fields.append('notes')
        if business_service is not None and visit.pk == anchor.pk:
            visit.business_service = business_service
            update_fields.append('business_service')
        visit.save(skip_capacity=True, update_fields=update_fields)
        updated_by_id[visit.pk] = visit
    updated = [updated_by_id[v.pk] for v, _s, _e in proposed]

    calendar_notices = 0
    calendar_errors: list[str] = []
    for visit in updated:
        if not visit_calendar.calendar_ics_in_play(visit):
            continue
        try:
            visit_calendar.notify_staff_schedule_change(
                visit,
                immediate=immediate_calendar,
                cancelled=False,
                request=request,
            )
            calendar_notices += 1
        except VisitEmailError as exc:
            calendar_errors.append(str(exc))

    return SeriesOpResult(
        updated=updated,
        unchanged_other_statuses=unchanged,
        calendar_notices=calendar_notices,
        calendar_errors=calendar_errors,
    )


@transaction.atomic
def cancel_scheduled_series(
    anchor: Visit,
    *,
    immediate_calendar: bool = False,
    request=None,
) -> SeriesOpResult:
    """Cancel/remove all still-scheduled visits in the series (C4 rules per visit)."""
    if not anchor.series_id:
        raise ValidationError('This visit is not part of a repeat series.')

    visits = list(scheduled_series_visits(anchor))
    if not visits:
        raise ValidationError('No scheduled visits left in this series.')

    unchanged = (
        Visit.objects.filter(series_id=anchor.series_id)
        .exclude(status=Visit.Status.SCHEDULED)
        .count()
    )

    updated: list[Visit] = []
    calendar_notices = 0
    calendar_errors: list[str] = []
    hard_deleted = 0

    for visit in visits:
        if visit_calendar.can_hard_delete_visit(visit):
            visit.delete()
            hard_deleted += 1
            continue
        visit_calendar.soft_cancel_visit(visit)
        updated.append(visit)
        try:
            visit_calendar.notify_staff_schedule_change(
                visit,
                immediate=immediate_calendar,
                cancelled=True,
                request=request,
            )
            calendar_notices += 1
        except VisitEmailError as exc:
            calendar_errors.append(str(exc))

    return SeriesOpResult(
        updated=updated,
        unchanged_other_statuses=unchanged,
        calendar_notices=calendar_notices,
        calendar_errors=calendar_errors,
        hard_deleted=hard_deleted,
    )


def cancel_scheduled_series_counts(anchor: Visit) -> tuple[int, int]:
    """Return (scheduled_count, other_status_count) for confirm copy."""
    if not anchor.series_id:
        return (0, 0)
    scheduled = scheduled_series_visits(anchor).count()
    other = (
        Visit.objects.filter(series_id=anchor.series_id)
        .exclude(status=Visit.Status.SCHEDULED)
        .count()
    )
    return scheduled, other
