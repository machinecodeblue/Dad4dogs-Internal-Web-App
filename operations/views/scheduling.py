from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from operations.capacity import assess_capacity
from operations.forms import TimelineForwardForm, TimelineMomentForm, VisitForm
from operations.models import ClientProfile, PendingCalendarEvent, Visit, VisitTimelineEvent
from operations.services.geolocation import resolve_timeline_coordinates
from operations.services.timeline_media import (
    TimelineMediaError,
    forward_timeline_event,
    log_moment_for_visits,
    visits_available_for_forward,
)
from operations.services.timeline_visits import active_checked_in_visits
from operations.services.agenda import (
    build_month_calendar,
    month_bounds,
    shift_month,
    visits_for_day,
)
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from operations.services.ical_feed import generate_ical_feed
from operations.services.feed_interactions import build_checkin_feed_activity
from operations.services.visit_email import VisitEmailError, send_booking_confirmation
from operations.services.visit_repeat import FREQUENCY_NONE, repeat_summary


def _apply_visit_form_errors(form, error: ValidationError):
    if hasattr(error, 'message_dict'):
        for field, errs in error.message_dict.items():
            for err in errs:
                form.add_error(field if field in form.fields else None, err)
    else:
        form.add_error(None, '; '.join(error.messages))


@login_required
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
        if not 1 <= cal_month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        cal_year = selected_date.year
        cal_month = selected_date.month

    month_first, month_last = month_bounds(cal_year, cal_month)
    if selected_date < month_first or selected_date > month_last:
        if date_param:
            pass
        elif request.GET.get('year') or request.GET.get('month'):
            selected_date = month_first

    agenda_visits = visits_for_day(selected_date)
    capacity = assess_capacity(selected_date)
    calendar_weeks = build_month_calendar(cal_year, cal_month, selected_date, today)
    prev_year, prev_month = shift_month(cal_year, cal_month, -1)
    next_year, next_month = shift_month(cal_year, cal_month, 1)

    pending_events = PendingCalendarEvent.objects.filter(
        review_status=PendingCalendarEvent.ReviewStatus.PENDING,
    )[:5]

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
        'approved_clients': ClientProfile.objects.filter(
            pipeline_stage=ClientProfile.PipelineStage.APPROVED,
        ).count(),
    })


@login_required
def mobile_checkin(request):
    today = timezone.localdate()
    visits = Visit.objects.filter(
        scheduled_start__date__lte=today,
        scheduled_end__date__gte=today,
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN],
    ).select_related('client').order_by('scheduled_start')
    capacity = assess_capacity(today)
    return render(request, 'operations/mobile_checkin.html', {
        'visits': visits,
        'capacity': capacity,
        'today': today,
    })


@login_required
@require_GET
def checkin_feed_activity(request):
    """Lightweight JSON poll — owner reactions/comments on checked-in dogs."""
    today = timezone.localdate()
    client_ids = list(
        Visit.objects.filter(
            scheduled_start__date__lte=today,
            scheduled_end__date__gte=today,
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
        visit.check_in()
        if capacity['status'] == 'warning':
            messages.warning(request, capacity['message'])
        messages.success(request, f'{visit.client.dog_name} checked in.')
    return redirect('operations:mobile_checkin')


@login_required
@require_POST
def visit_check_out(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    visit.check_out()
    messages.success(
        request,
        f'{visit.client.dog_name} checked out. Fee: ${visit.calculated_fee} CAD',
    )
    return redirect('operations:mobile_checkin')


@login_required
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


@login_required
def visit_create(request, pk):
    client = get_object_or_404(ClientProfile, pk=pk)
    client_visits = client.visits.filter(
        status=Visit.Status.COMPLETED,
    )[:10]
    visit_form = VisitForm(client=client)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            visit_form = VisitForm(request.POST, client=client)
            if visit_form.is_valid():
                try:
                    visits = visit_form.save_all()
                    if len(visits) > 1:
                        pairs = [(v.scheduled_start, v.scheduled_end) for v in visits]
                        freq = visit_form.cleaned_data.get('repeat_frequency', FREQUENCY_NONE)
                        interval = visit_form.cleaned_data.get('repeat_interval') or 1
                        summary = repeat_summary(pairs, freq, interval)
                        messages.success(
                            request,
                            f'Scheduled {client.dog_name}: {summary}',
                        )
                    else:
                        messages.success(
                            request,
                            f'Scheduled {client.dog_name}: {visits[0].schedule_display}',
                        )
                    if visit_form.cleaned_data.get('send_confirmation_email'):
                        try:
                            send_booking_confirmation(client, visits)
                            messages.success(
                                request,
                                f'Confirmation email sent to {client.owner_email}.',
                            )
                        except VisitEmailError as exc:
                            messages.warning(
                                request,
                                f'Visit booked, but confirmation email was not sent: {exc}',
                            )
                    return redirect('operations:dog_detail', pk=client.pk)
                except ValidationError as e:
                    _apply_visit_form_errors(visit_form, e)
        elif action == 'clone':
            new_date_str = request.POST.get('new_date', '').strip()
            new_date_text = request.POST.get('new_date_text', '').strip()
            visit_id = request.POST.get('visit_id')
            if not visit_id:
                messages.error(request, 'Select a past visit to clone.')
            else:
                source = get_object_or_404(Visit, pk=visit_id, client=client)
                try:
                    if new_date_str:
                        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    elif new_date_text:
                        new_date = parse_datetime_text(new_date_text).date()
                    else:
                        raise ValidationError('Enter the new start date.')
                    cloned = source.clone_to_date(new_date)
                    messages.success(
                        request,
                        f'Cloned visit for {client.dog_name}: {cloned.schedule_display}',
                    )
                    return redirect('operations:dog_detail', pk=client.pk)
                except ValidationError as e:
                    messages.error(request, '; '.join(e.messages))

    return render(request, 'operations/visit_form.html', {
        'client': client,
        'visits': client_visits,
        'visit_form': visit_form,
        'visit': None,
        'title': f'Schedule Visit — {client.dog_name}',
        'submit_label': 'Schedule Visit',
        'show_clone': True,
    })


@login_required
def duplicate_visit(request, pk):
    """Legacy URL — same as visit_create."""
    return visit_create(request, pk)


@login_required
def visit_edit(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be edited.')
        return redirect('operations:dog_detail', pk=visit.client_id)

    visit_form = VisitForm(instance=visit)
    if request.method == 'POST':
        visit_form = VisitForm(request.POST, instance=visit)
        if visit_form.is_valid():
            try:
                visit = visit_form.save()
                messages.success(
                    request,
                    f'Updated visit for {visit.client.dog_name}: {visit.schedule_display}',
                )
                return redirect('operations:dog_detail', pk=visit.client_id)
            except ValidationError as e:
                _apply_visit_form_errors(visit_form, e)

    return render(request, 'operations/visit_form.html', {
        'client': visit.client,
        'visit_form': visit_form,
        'title': f'Edit Visit — {visit.client.dog_name}',
        'submit_label': 'Save Visit',
        'show_clone': False,
        'visit': visit,
    })


@login_required
@require_POST
def visit_delete(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    dog_pk = visit.client_id
    dog_name = visit.client.dog_name
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be removed.')
        return redirect('operations:dog_detail', pk=dog_pk)
    visit.delete()
    messages.success(request, f'Removed scheduled visit for {dog_name}.')
    return redirect('operations:dog_detail', pk=dog_pk)


@login_required
def pending_events(request):
    events = PendingCalendarEvent.objects.filter(
        review_status=PendingCalendarEvent.ReviewStatus.PENDING,
    ).select_related('matched_client')
    return render(request, 'operations/pending_events.html', {'events': events})


@login_required
@require_POST
def approve_pending_event(request, pk):
    event = get_object_or_404(PendingCalendarEvent, pk=pk)
    if event.matched_client:
        Visit.objects.create(
            client=event.matched_client,
            scheduled_start=event.start_datetime,
            scheduled_end=event.end_datetime,
            notes=f'From calendar: {event.summary}',
        )
        event.review_status = PendingCalendarEvent.ReviewStatus.APPROVED
        event.save()
        messages.success(request, 'Calendar event approved and visit created.')
    else:
        messages.error(request, 'No matched client — assign a client in admin first.')
    return redirect('operations:pending_events')


@login_required
@require_POST
def reject_pending_event(request, pk):
    event = get_object_or_404(PendingCalendarEvent, pk=pk)
    event.review_status = PendingCalendarEvent.ReviewStatus.REJECTED
    event.save()
    messages.info(request, 'Event rejected.')
    return redirect('operations:pending_events')


def _timeline_eligible_visits():
    return active_checked_in_visits()


@login_required
def visit_timeline(request, pk):
    """Contemporaneous photo/video log for an actively checked-in visit."""
    visit = get_object_or_404(
        Visit.objects.select_related('client'),
        pk=pk,
    )
    if not visit.accepts_timeline_events:
        messages.error(
            request,
            'Timeline logging is only available while the dog is checked in.',
        )
        return redirect('operations:mobile_checkin')

    eligible_visits = _timeline_eligible_visits()

    if request.method == 'POST':
        form = TimelineMomentForm(
            request.POST,
            request.FILES,
            eligible_visits=eligible_visits,
        )
        if form.is_valid():
            lat, lng, used_fallback, fallback_label = resolve_timeline_coordinates(
                form.cleaned_data.get('latitude'),
                form.cleaned_data.get('longitude'),
            )
            try:
                _, events = log_moment_for_visits(
                    visits=list(form.cleaned_data['visit_ids']),
                    media_kind=form.cleaned_data['media_kind'],
                    uploaded_file=form.cleaned_data['uploaded_file'],
                    caption_notes=form.cleaned_data.get('caption_notes', ''),
                    latitude=lat,
                    longitude=lng,
                    used_fallback=used_fallback,
                    fallback_label=fallback_label,
                )
                dog_names = ', '.join(e.visit.client.dog_name for e in events)
                if used_fallback:
                    messages.warning(
                        request,
                        f'Moment logged for {dog_names}. GPS unavailable — site location used.',
                    )
                else:
                    messages.success(request, f'Moment logged for {dog_names}.')
            except TimelineMediaError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, form.errors.as_text())
        return redirect('operations:visit_timeline', pk=visit.pk)

    events = visit.timeline_events.select_related(
        'media_asset',
        'source_event__visit__client',
    )
    forward_forms = []
    for event in events:
        targets = visits_available_for_forward(event)
        if targets.exists():
            forward_forms.append({
                'event': event,
                'form': TimelineForwardForm(eligible_visits=targets),
            })

    return render(request, 'operations/visit_timeline.html', {
        'visit': visit,
        'dog': visit.client,
        'events': events,
        'eligible_visits': eligible_visits,
        'form': TimelineMomentForm(
            eligible_visits=eligible_visits,
            initial={'visit_ids': [visit.pk]},
        ),
        'forward_forms': forward_forms,
    })


@login_required
@require_POST
def visit_timeline_forward(request, pk, event_pk):
    visit = get_object_or_404(Visit.objects.select_related('client'), pk=pk)
    if not visit.accepts_timeline_events:
        messages.error(request, 'Forwarding is only available during an active check-in.')
        return redirect('operations:mobile_checkin')

    source_event = get_object_or_404(
        VisitTimelineEvent.objects.select_related('media_asset', 'visit__client'),
        pk=event_pk,
        visit=visit,
    )
    targets = visits_available_for_forward(source_event)
    form = TimelineForwardForm(request.POST, eligible_visits=targets)
    if form.is_valid():
        try:
            created = forward_timeline_event(
                source_event=source_event,
                target_visit_ids=[v.pk for v in form.cleaned_data['visit_ids']],
            )
            names = ', '.join(e.visit.client.dog_name for e in created)
            messages.success(request, f'Shared with {names}. Original capture time preserved.')
        except TimelineMediaError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, form.errors.as_text())
    return redirect('operations:visit_timeline', pk=visit.pk)


def ical_feed(request):
    """Public read-only iCal feed for Google Calendar subscription."""
    return generate_ical_feed()