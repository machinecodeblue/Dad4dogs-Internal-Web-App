"""Public capability-URL page for clients to confirm, reschedule, or cancel."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from operations.forms.scheduling.booking_manage import BookingRescheduleForm
from operations.models import Visit
from operations.services import visit_calendar
from operations.services.datetime_parse import format_datetime_display
from operations.services.visit_email import VisitEmailError, send_booking_ics_invite


def _context(visit: Visit, *, reschedule_form=None, flash=None):
    siblings = list(visit_calendar.series_siblings_awaiting_confirm(visit))
    awaiting_cancel = (
        visit.status == Visit.Status.CANCELLED
        and visit.calendar_invite_state == Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM
    )
    return {
        'visit': visit,
        'dog': visit.client,
        'service': visit.business_service,
        'state': visit.calendar_invite_state,
        'awaiting_cancel_confirm': awaiting_cancel,
        'schedule_label': (
            f'{format_datetime_display(visit.scheduled_start)}'
            f' – {format_datetime_display(visit.scheduled_end)}'
        ),
        'series_awaiting': siblings,
        'can_confirm_series': (
            visit.calendar_invite_state == Visit.CalendarInviteState.AWAITING_CONFIRM
            and bool(siblings)
        ),
        'reschedule_form': reschedule_form or BookingRescheduleForm(visit=visit),
        'flash': flash,
    }


def _send_ics(visit: Visit, *, method: str = 'REQUEST', request=None) -> None:
    send_booking_ics_invite(
        visit.client, [visit], method=method, request=request,
    )


@require_http_methods(['GET', 'POST'])
def booking_manage(request, token):
    visit = visit_calendar.resolve_visit_by_manage_token(token)
    if visit is None:
        return render(request, 'operations/booking_manage_missing.html', status=404)

    if request.method == 'GET':
        return render(request, 'operations/booking_manage.html', _context(visit))

    action = (request.POST.get('action') or '').strip()
    try:
        if action == 'confirm':
            if visit.calendar_invite_state != Visit.CalendarInviteState.AWAITING_CONFIRM:
                messages.info(request, 'This booking was already confirmed.')
            else:
                visit_calendar.confirm_visit(visit)
                try:
                    _send_ics(visit, request=request)
                    messages.success(
                        request,
                        'Thanks — your booking is confirmed. Check your email for the calendar invite.',
                    )
                except VisitEmailError as exc:
                    messages.warning(
                        request,
                        f'Booking confirmed, but the calendar invite email failed: {exc}',
                    )
        elif action == 'confirm_series':
            if visit.calendar_invite_state != Visit.CalendarInviteState.AWAITING_CONFIRM:
                messages.info(request, 'This booking was already confirmed.')
            else:
                confirmed = visit_calendar.confirm_series_awaiting(visit)
                try:
                    send_booking_ics_invite(
                        visit.client, confirmed, request=request,
                    )
                    messages.success(
                        request,
                        f'Confirmed {len(confirmed)} visits. Check your email for the calendar invite.',
                    )
                except VisitEmailError as exc:
                    messages.warning(
                        request,
                        f'Visits confirmed, but the calendar invite email failed: {exc}',
                    )
        elif action == 'approve_change':
            if visit.calendar_invite_state != Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM:
                messages.info(request, 'There is no pending schedule change to approve.')
            elif visit.status == Visit.Status.CANCELLED:
                visit_calendar.bump_ics_sequence(visit)
                visit.calendar_invite_state = Visit.CalendarInviteState.CANCELLED_INVITE
                visit.save(update_fields=['calendar_invite_state', 'updated_at'])
                try:
                    _send_ics(visit, method='CANCEL', request=request)
                    messages.success(
                        request,
                        'Cancellation confirmed. A calendar removal email is on its way.',
                    )
                except VisitEmailError as exc:
                    messages.warning(
                        request,
                        f'Cancellation confirmed, but the calendar email failed: {exc}',
                    )
            else:
                visit_calendar.approve_staff_change(visit)
                visit.refresh_from_db()
                visit_calendar.bump_ics_sequence(visit)
                try:
                    _send_ics(visit, request=request)
                    messages.success(request, 'Schedule change approved. Calendar update emailed.')
                except VisitEmailError as exc:
                    messages.warning(
                        request,
                        f'Schedule approved, but the calendar update email failed: {exc}',
                    )
        elif action == 'reschedule':
            if visit.status == Visit.Status.CANCELLED:
                messages.error(request, 'This booking is cancelled and cannot be rescheduled here.')
            else:
                form = BookingRescheduleForm(request.POST, visit=visit)
                if not form.is_valid():
                    return render(
                        request,
                        'operations/booking_manage.html',
                        _context(visit, reschedule_form=form),
                    )
                prior_state = visit.calendar_invite_state
                visit_calendar.apply_client_reschedule(
                    visit,
                    start=form.cleaned_data['scheduled_start'],
                    end=form.cleaned_data['scheduled_end'],
                )
                if prior_state in {
                    Visit.CalendarInviteState.INVITE_ISSUED,
                    Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM,
                }:
                    visit_calendar.bump_ics_sequence(visit)
                    try:
                        _send_ics(visit, request=request)
                        messages.success(
                            request,
                            'Schedule updated. A calendar update email is on its way.',
                        )
                    except VisitEmailError as exc:
                        messages.warning(
                            request,
                            f'Schedule updated, but the calendar email failed: {exc}',
                        )
                else:
                    messages.success(request, 'Schedule updated.')
        elif action == 'cancel':
            if visit.calendar_invite_state == Visit.CalendarInviteState.CANCELLED_INVITE:
                messages.info(request, 'This booking is already cancelled.')
            elif visit.status == Visit.Status.CANCELLED:
                messages.info(request, 'This booking is already cancelled.')
            elif visit.status != Visit.Status.SCHEDULED:
                messages.error(
                    request,
                    'This visit can no longer be cancelled here. Please contact Dad4dogs.',
                )
            else:
                ics_was_in_play = visit_calendar.calendar_ics_in_play(visit)
                visit_calendar.cancel_via_manage(visit)
                if ics_was_in_play:
                    visit_calendar.bump_ics_sequence(visit)
                    try:
                        _send_ics(visit, method='CANCEL', request=request)
                        messages.success(
                            request,
                            'Booking cancelled. A calendar cancellation email is on its way.',
                        )
                    except VisitEmailError as exc:
                        messages.warning(
                            request,
                            f'Booking cancelled, but the calendar email failed: {exc}',
                        )
                else:
                    messages.success(request, 'Booking cancelled.')
        else:
            messages.error(request, 'Unknown action.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))

    visit.refresh_from_db()
    return redirect('operations:booking_manage', token=visit.calendar_manage_token)
