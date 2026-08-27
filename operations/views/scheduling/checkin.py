from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from operations.capacity import assess_capacity
from operations.models import Visit
from operations.services.agenda import day_bounds
from operations.services.feed_interactions import build_checkin_feed_activity
from operations.views.scheduling.helpers import parse_local_datetime_input


@login_required
@require_GET
def mobile_checkin(request):
    today = timezone.localdate()
    day_start, day_end = day_bounds(today)
    day_filter = {
        'scheduled_start__lt': day_end,
        'scheduled_end__gt': day_start,
    }
    visits = Visit.objects.filter(
        **day_filter,
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN],
    ).select_related('client').order_by('scheduled_start')
    completed_visits = Visit.objects.filter(
        **day_filter,
        status=Visit.Status.COMPLETED,
    ).select_related('client').order_by('-actual_departure', '-scheduled_end')
    capacity = assess_capacity(today)
    return render(request, 'operations/mobile_checkin.html', {
        'visits': visits,
        'completed_visits': completed_visits,
        'capacity': capacity,
        'today': today,
    })


@login_required
@require_GET
def checkin_feed_activity(request):
    """Lightweight JSON poll — owner reactions/comments on checked-in dogs."""
    today = timezone.localdate()
    day_start, day_end = day_bounds(today)
    client_ids = list(
        Visit.objects.filter(
            scheduled_start__lt=day_end,
            scheduled_end__gt=day_start,
            status=Visit.Status.CHECKED_IN,
        ).values_list('client_id', flat=True)
    )
    since = None
    since_param = (request.GET.get('since') or '').strip()
    if since_param:
        since = parse_datetime(since_param)
    payload = build_checkin_feed_activity(client_ids, since=since)
    return JsonResponse(payload)


@login_required
@require_POST
def visit_check_in(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    capacity = assess_capacity(timezone.localdate(), exclude_visit_id=visit.pk)
    if capacity['status'] == 'blocked':
        messages.error(request, capacity['message'])
    else:
        try:
            visit.check_in()
        except ValidationError as e:
            messages.error(request, '; '.join(e.messages))
        else:
            if capacity['status'] == 'warning':
                messages.warning(request, capacity['message'])
            messages.success(request, f'{visit.client.dog_name} checked in.')
    return redirect('operations:mobile_checkin')


@login_required
@require_POST
def visit_check_out(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    try:
        visit.check_out()
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    else:
        messages.success(
            request,
            f'{visit.client.dog_name} checked out. Fee: ${visit.calculated_fee} CAD',
        )
    return redirect('operations:mobile_checkin')


@login_required
@require_POST
def visit_update_actual_times(request, pk):
    """Correct actual arrival/departure after a late tap; recalculate fee if completed."""
    visit = get_object_or_404(Visit, pk=pk)
    arrival_raw = (request.POST.get('actual_arrival') or '').strip()
    departure_raw = (request.POST.get('actual_departure') or '').strip()
    try:
        arrival = parse_local_datetime_input(arrival_raw) if arrival_raw else None
        departure = None
        if visit.status == Visit.Status.COMPLETED:
            if not departure_raw:
                raise ValidationError('Enter the actual departure time.')
            departure = parse_local_datetime_input(departure_raw)
        visit.update_actual_times(arrival=arrival, departure=departure)
    except ValidationError as e:
        messages.error(request, '; '.join(e.messages))
    else:
        if visit.status == Visit.Status.COMPLETED:
            messages.success(
                request,
                f'{visit.client.dog_name} times updated. Fee: ${visit.calculated_fee} CAD',
            )
        else:
            messages.success(request, f'{visit.client.dog_name} arrival time updated.')
    return redirect('operations:mobile_checkin')