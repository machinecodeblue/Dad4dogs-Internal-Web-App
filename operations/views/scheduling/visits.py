from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from operations.forms import VisitForm
from operations.models import ClientProfile, Visit
from operations.services import visit_calendar
from operations.services.datetime_parse import parse_datetime_text
from operations.services.visit_email import VisitEmailError, send_booking_review_link
from operations.services.visit_repeat import FREQUENCY_NONE, repeat_summary
from operations.services.visit_series_ops import (
    cancel_scheduled_series,
    cancel_scheduled_series_counts,
    series_has_scheduled_siblings,
    shift_scheduled_series,
)
from operations.views.scheduling.helpers import apply_visit_form_errors


@login_required
@require_http_methods(['GET', 'POST'])
def visit_create(request, pk):
    from operations.services.pipeline import INITIAL_EVALUATION_SLUG, MEET_GREET_SLUG

    client = get_object_or_404(ClientProfile, pk=pk)
    preferred_slug = (request.GET.get('service') or '').strip()
    if preferred_slug == MEET_GREET_SLUG:
        return redirect('operations:schedule_meet_greet', pk=client.pk)
    if preferred_slug == INITIAL_EVALUATION_SLUG:
        return redirect('operations:schedule_evaluation', pk=client.pk)

    client_visits = client.visits.filter(status=Visit.Status.COMPLETED)[:10]
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
                        messages.success(request, f'Scheduled {client.dog_name}: {summary}')
                    else:
                        messages.success(request, f'Scheduled {client.dog_name}: {visits[0].schedule_display}')
                    if visit_form.cleaned_data.get('send_confirmation_email'):
                        try:
                            send_booking_review_link(client, visits, request=request)
                            messages.success(
                                request,
                                f'Review & confirm link sent to {client.owner_email}.',
                            )
                        except VisitEmailError as exc:
                            messages.warning(
                                request,
                                f'Visit booked, but review email was not sent: {exc}',
                            )
                    return redirect('operations:dog_detail', pk=client.pk)
                except ValidationError as e:
                    apply_visit_form_errors(visit_form, e)
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
                    messages.success(request, f'Cloned visit for {client.dog_name}: {cloned.schedule_display}')
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
@require_http_methods(['GET', 'POST'])
def duplicate_visit(request, pk):
    """Legacy URL — same as visit_create."""
    return visit_create(request, pk)


@login_required
@require_http_methods(['GET', 'POST'])
def visit_edit(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('series', 'client'), pk=pk)
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be edited.')
        return redirect('operations:dog_detail', pk=visit.client_id)

    visit_form = VisitForm(instance=visit)
    if request.method == 'POST':
        prior_start = visit.scheduled_start
        prior_end = visit.scheduled_end
        prior_service_id = visit.business_service_id
        calendar_was_active = visit_calendar.calendar_ics_in_play(visit)
        visit_form = VisitForm(request.POST, instance=visit)
        if visit_form.is_valid():
            try:
                apply_series = visit_form.cleaned_data.get('apply_to_series') == 'series'
                new_start = visit_form.cleaned_data['scheduled_start']
                new_end = visit_form.cleaned_data['scheduled_end']
                new_service = visit_form.cleaned_data.get('business_service')
                new_service_id = new_service.pk if new_service is not None else None
                immediate = bool(
                    visit_form.cleaned_data.get('send_calendar_invite_immediately')
                )
                schedule_changed = (
                    new_start != prior_start
                    or new_end != prior_end
                    or new_service_id != prior_service_id
                )

                if apply_series and schedule_changed:
                    result = shift_scheduled_series(
                        visit,
                        prior_start=prior_start,
                        prior_end=prior_end,
                        new_start=new_start,
                        new_end=new_end,
                        notes=visit_form.cleaned_data.get('notes', ''),
                        business_service=visit_form.cleaned_data.get('business_service'),
                        immediate_calendar=immediate,
                        request=request,
                    )
                    messages.success(
                        request,
                        f'Updated {len(result.updated)} scheduled visit(s) in the series '
                        f'for {visit.client.dog_name}.',
                    )
                    if result.unchanged_other_statuses:
                        messages.info(
                            request,
                            f'{result.unchanged_other_statuses} checked-in/completed/'
                            f'cancelled visit(s) in the series were left unchanged.',
                        )
                    for err in result.calendar_errors:
                        messages.warning(request, f'Calendar email issue: {err}')
                else:
                    visit = visit_form.save()
                    messages.success(
                        request,
                        f'Updated visit for {visit.client.dog_name}: {visit.schedule_display}',
                    )
                    if calendar_was_active and schedule_changed:
                        try:
                            cal_result = visit_calendar.notify_staff_schedule_change(
                                visit,
                                immediate=immediate,
                                cancelled=False,
                                request=request,
                            )
                            if cal_result == 'ics_request':
                                messages.success(
                                    request,
                                    f'Updated calendar invite sent to {visit.client.owner_email}.',
                                )
                            else:
                                messages.success(
                                    request,
                                    f'Schedule-change review link sent to {visit.client.owner_email}.',
                                )
                        except VisitEmailError as exc:
                            messages.warning(
                                request,
                                f'Visit updated, but calendar email was not sent: {exc}',
                            )
                return redirect('operations:dog_detail', pk=visit.client_id)
            except ValidationError as e:
                apply_visit_form_errors(visit_form, e)

    series_scheduled_count, _other = cancel_scheduled_series_counts(visit)
    return render(request, 'operations/visit_form.html', {
        'client': visit.client,
        'visit_form': visit_form,
        'title': f'Edit Visit — {visit.client.dog_name}',
        'submit_label': 'Save Visit',
        'show_clone': False,
        'visit': visit,
        'show_calendar_cancel_options': visit_calendar.calendar_ics_in_play(visit),
        'show_series_cancel_options': series_has_scheduled_siblings(visit),
        'series_scheduled_count': series_scheduled_count,
    })


@login_required
@require_POST
def visit_send_confirmation(request, pk):
    """Email a booking confirmation for one visit that has not been sent yet."""
    visit = get_object_or_404(Visit.objects.select_related('client'), pk=pk)
    dog_pk = visit.client_id
    if visit.status == Visit.Status.CANCELLED:
        messages.error(request, 'Cancelled visits cannot be emailed.')
        return redirect('operations:dog_detail', pk=dog_pk)
    if visit.calendar_review_sent_at or visit.calendar_invite_state != Visit.CalendarInviteState.NONE:
        messages.info(request, 'A review or calendar email was already started for this visit.')
        return redirect('operations:dog_detail', pk=dog_pk)
    try:
        send_booking_review_link(visit.client, [visit], request=request)
        messages.success(request, f'Review & confirm link sent to {visit.client.owner_email}.')
    except VisitEmailError as exc:
        messages.warning(request, f'Review email was not sent: {exc}')
    return redirect('operations:dog_detail', pk=dog_pk)


@login_required
@require_POST
def visit_delete(request, pk):
    visit = get_object_or_404(
        Visit.objects.select_related('client', 'series'),
        pk=pk,
    )
    dog_pk = visit.client_id
    dog_name = visit.client.dog_name
    if not visit.is_editable:
        messages.error(request, 'Only scheduled visits can be removed.')
        return redirect('operations:dog_detail', pk=dog_pk)

    immediate = request.POST.get('send_calendar_invite_immediately') in {
        'on', 'true', '1', 'yes',
    }
    apply_series = request.POST.get('apply_to_series') == 'series'

    if apply_series and visit.series_id:
        try:
            result = cancel_scheduled_series(
                visit,
                immediate_calendar=immediate,
                request=request,
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))
            return redirect('operations:visit_edit', pk=visit.pk)
        removed = len(result.updated) + result.hard_deleted
        messages.success(
            request,
            f'Cancelled/removed {removed} scheduled visit(s) in the series for {dog_name}.',
        )
        if result.unchanged_other_statuses:
            messages.info(
                request,
                f'{result.unchanged_other_statuses} checked-in/completed/'
                f'cancelled visit(s) in the series were left unchanged.',
            )
        for err in result.calendar_errors:
            messages.warning(request, f'Calendar email issue: {err}')
        return redirect('operations:dog_detail', pk=dog_pk)

    if visit_calendar.can_hard_delete_visit(visit):
        visit.delete()
        messages.success(request, f'Removed scheduled visit for {dog_name}.')
        return redirect('operations:dog_detail', pk=dog_pk)

    # Invited visits: soft-cancel so UID/SEQUENCE survive for METHOD:CANCEL.
    visit_calendar.soft_cancel_visit(visit)
    try:
        cal_result = visit_calendar.notify_staff_schedule_change(
            visit,
            immediate=immediate,
            cancelled=True,
            request=request,
        )
        if cal_result == 'ics_cancel':
            messages.success(
                request,
                f'Cancelled {dog_name}\'s visit and sent a calendar cancellation.',
            )
        else:
            messages.success(
                request,
                f'Cancelled {dog_name}\'s visit. Cancellation review link emailed '
                f'to {visit.client.owner_email}.',
            )
    except VisitEmailError as exc:
        messages.warning(
            request,
            f'Visit cancelled, but calendar email was not sent: {exc}',
        )
    return redirect('operations:dog_detail', pk=dog_pk)