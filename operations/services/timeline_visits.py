from django.utils import timezone

from operations.models import Visit


def active_checked_in_visits(*, exclude_visit_id: int | None = None):
    """Visits currently checked in and overlapping today — eligible for timeline share."""
    today = timezone.localdate()
    qs = Visit.objects.filter(
        status=Visit.Status.CHECKED_IN,
        scheduled_start__date__lte=today,
        scheduled_end__date__gte=today,
    ).select_related('client').order_by('client__dog_name')
    if exclude_visit_id:
        qs = qs.exclude(pk=exclude_visit_id)
    return qs