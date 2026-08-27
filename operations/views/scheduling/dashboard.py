from datetime import MAXYEAR, MINYEAR, date, datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from operations.capacity import assess_capacity
from operations.models import ClientProfile, PendingCalendarEvent
from operations.services.agenda import (
    build_month_calendar,
    month_bounds,
    shift_month,
    visits_for_day,
)
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from operations.services.ical_feed import generate_ical_feed


@login_required
@require_GET
def dashboard(request):
    today = timezone.localdate()

    selected_date = today
    date_param = request.GET.get('date', '').strip()
    if date_param:
        try:
            selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today

    try:
        cal_year = int(request.GET.get('year', selected_date.year))
        cal_month = int(request.GET.get('month', selected_date.month))
        if not 1 <= cal_month <= 12 or not MINYEAR <= cal_year <= MAXYEAR:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        cal_year = selected_date.year
        cal_month = selected_date.month

    month_first, month_last = month_bounds(cal_year, cal_month)
    if selected_date < month_first or selected_date > month_last:
        if not date_param and (request.GET.get('year') or request.GET.get('month')):
            selected_date = month_first

    agenda_visits = visits_for_day(selected_date)
    capacity = assess_capacity(selected_date)
    calendar_weeks = build_month_calendar(cal_year, cal_month, selected_date, today)
    prev_year, prev_month = shift_month(cal_year, cal_month, -1)
    next_year, next_month = shift_month(cal_year, cal_month, 1)

    pending_events = PendingCalendarEvent.objects.filter(
        review_status=PendingCalendarEvent.ReviewStatus.PENDING,
    )[:5]

    vax_counts = ClientProfile.objects.visible().vaccination_status_counts()

    return render(request, 'operations/dashboard.html', {
        'today': today,
        'selected_date': selected_date,
        'agenda_visits': agenda_visits,
        'capacity': capacity,
        'calendar_weeks': calendar_weeks,
        'cal_year': cal_year,
        'cal_month': cal_month,
        'cal_month_label': date(cal_year, cal_month, 1).strftime('%B %Y'),
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'pending_events': pending_events,
        'approved_clients': ClientProfile.objects.visible().filter(
            pipeline_stage=ClientProfile.PipelineStage.APPROVED,
        ).count(),
        'vax_expiring_count': vax_counts['expiring'],
        'vax_expired_count': vax_counts['expired'],
    })


@login_required
@require_GET
def parse_datetime_field(request):
    """Preview parse for a free-text date/time field (blur on visit form)."""
    text = request.GET.get('q', '').strip()
    default_iso = request.GET.get('default', '').strip()
    default = None
    if default_iso:
        try:
            default = parse_datetime_text(default_iso)
        except ValueError:
            pass
    try:
        parsed = parse_datetime_text(text, default=default)
    except ValueError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)})
    return JsonResponse({
        'ok': True,
        'display': format_datetime_display(parsed),
        'iso': parsed.isoformat(),
    })


@require_GET
def ical_feed(request):
    """Public read-only iCal feed for Google Calendar subscription."""
    return generate_ical_feed()