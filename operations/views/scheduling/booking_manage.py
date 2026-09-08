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
    return {
        'visit': visit,
        'dog': visit.client,
        'service': visit.business_service,
        'state': visit.calendar_invite_state,
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
                    send_booking_ics_invite(visit.client, [visit])
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
                    send_booking_ics_invite(visit.client, confirmed)
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
            visit_calendar.approve_staff_change(visit)
            visit.refresh_from_db()
            visit.ics_sequence = int(visit.ics_sequence or 0) + 1
            visit.save(update_fields=['ics_sequence', 'updated_at'])
            try:
                send_booking_ics_invite(visit.client, [visit])
                messages.success(request, 'Schedule change approved. Calendar update emailed.')
            except VisitEmailError as exc:
                messages.warning(
                    request,
                    f'Schedule approved, but the calendar update email failed: {exc}',
                )
        elif action == 'reschedule':
            form = BookingRescheduleForm(request.POST, visit=visit)
            if not form.is_valid():
                return render(
                    request,
                    'operations/booking_manage.html',
                    _context(visit, reschedule_form=form),
                )
            visit_calendar.apply_client_reschedule(
                visit,
                start=form.cleaned_data['scheduled_start'],
                end=form.cleaned_data['scheduled_end'],
            )
            messages.success(request, 'Schedule updated.')
        elif action == 'cancel':
            if visit.status == Visit.Status.CANCELLED:
                messages.info(request, 'This booking is already cancelled.')
            elif visit.status != Visit.Status.SCHEDULED:
                messages.error(
                    request,
                    'This visit can no longer be cancelled here. Please contact Dad4dogs.',
                )
            else:
                visit_calendar.cancel_via_manage(visit)
                messages.success(request, 'Booking cancelled.')
        else:
            messages.error(request, 'Unknown action.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc))

    visit.refresh_from_db()
    return redirect('operations:booking_manage', token=visit.calendar_manage_token)
