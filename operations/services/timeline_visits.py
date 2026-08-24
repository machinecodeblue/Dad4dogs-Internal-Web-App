from django.utils import timezone

from operations.models import Visit
from operations.services.agenda import day_bounds


def active_checked_in_visits(*, exclude_visit_id: int | None = None):
    """Visits currently checked in and overlapping today — eligible for timeline share."""
    today = timezone.localdate()
    day_start, day_end = day_bounds(today)
    qs = Visit.objects.filter(
        status=Visit.Status.CHECKED_IN,
        scheduled_start__lt=day_end,
        scheduled_end__gt=day_start,
    ).select_related('client').order_by('client__dog_name')
    if exclude_visit_id:
        qs = qs.exclude(pk=exclude_visit_id)
    return qs