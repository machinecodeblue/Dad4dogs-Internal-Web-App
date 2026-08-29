from datetime import date, timedelta

from django.utils import timezone


def week_bounds(reference: date | None = None) -> tuple[date, date]:
    ref = reference or timezone.localdate()
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end
