from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms import TimelineForwardForm, TimelineMomentForm
from operations.models import Visit, VisitTimelineEvent
from operations.services.geolocation import resolve_timeline_coordinates
from operations.services.timeline_media import (
    TimelineMediaError,
    forward_timeline_event,
    log_moment_for_visits,
    visits_available_for_forward,
)
from operations.services.timeline_visits import active_checked_in_visits
from operations.views.scheduling.helpers import form_error_message


@login_required
@require_http_methods(['GET', 'POST'])
def visit_timeline(request, pk):
    """Contemporaneous photo/video log for an actively checked-in visit."""
    visit = get_object_or_404(Visit.objects.select_related('client'), pk=pk)
    if not visit.accepts_timeline_events:
        messages.error(request, 'Timeline logging is only available while the dog is checked in.')
        return redirect('operations:mobile_checkin')

    eligible_visits = active_checked_in_visits()

    if request.method == 'POST':
        form = TimelineMomentForm(request.POST, request.FILES, eligible_visits=eligible_visits)
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
                    messages.warning(request, f'Moment logged for {dog_names}. GPS unavailable — site location used.')
                else:
                    messages.success(request, f'Moment logged for {dog_names}.')
            except TimelineMediaError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, form_error_message(form))
        return redirect('operations:visit_timeline', pk=visit.pk)

    events = visit.timeline_events.select_related('media_asset', 'source_event__visit__client')
    forward_targets = eligible_visits.exclude(pk=visit.pk)
    forward_forms = []
    if forward_targets:
        shared_form = TimelineForwardForm(eligible_visits=forward_targets)
        for event in events:
            forward_forms.append({'event': event, 'form': shared_form})

    return render(request, 'operations/visit_timeline.html', {
        'visit': visit,
        'dog': visit.client,
        'events': events,
        'eligible_visits': eligible_visits,
        'form': TimelineMomentForm(eligible_visits=eligible_visits, initial={'visit_ids': [visit.pk]}),
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
        messages.error(request, form_error_message(form))
    return redirect('operations:visit_timeline', pk=visit.pk)