"""Client calendar invite lifecycle helpers (tokens, UID, series siblings)."""

from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.urls import reverse

from operations.models.scheduling import Visit

_TOKEN_BYTES = 24


def generate_manage_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def generate_unique_manage_token(*, max_attempts: int = 40) -> str:
    for _ in range(max_attempts):
        candidate = generate_manage_token()
        if not Visit.objects.filter(calendar_manage_token=candidate).exists():
            return candidate
    return uuid.uuid4().hex


def default_ics_uid(visit: Visit) -> str:
    """
    Stable unique UID for this visit row.

    Must NOT be only ``visit_{pk}@…`` — after a DB flush/reseed, primary keys
    recycle and Google Calendar keeps showing the previous dog's invite for
    that UID (ICS attachment can be correct while Gmail's invite card is not).
    """
    domain = getattr(settings, 'ICAL_UID_DOMAIN', 'dad4dogs.local')
    return f'visit-{visit.pk}-{uuid.uuid4().hex}@{domain}'


def is_legacy_pk_ics_uid(uid: str, visit: Visit) -> bool:
    """True for old ``visit_{pk}@domain`` UIDs that collide across reseeds."""
    if not uid or not visit.pk:
        return False
    domain = getattr(settings, 'ICAL_UID_DOMAIN', 'dad4dogs.local')
    return uid.strip().lower() == f'visit_{visit.pk}@{domain}'.lower()


def ensure_calendar_manage_token(visit: Visit, *, save: bool = True) -> str:
    if visit.calendar_manage_token:
        return visit.calendar_manage_token
    visit.calendar_manage_token = generate_unique_manage_token()
    if save and visit.pk:
        visit.save(update_fields=['calendar_manage_token', 'updated_at'])
    return visit.calendar_manage_token


def regenerate_calendar_manage_token(visit: Visit, *, save: bool = True) -> str:
    visit.calendar_manage_token = generate_unique_manage_token()
    if save and visit.pk:
        visit.save(update_fields=['calendar_manage_token', 'updated_at'])
    return visit.calendar_manage_token


def ensure_ics_uid(visit: Visit, *, save: bool = True) -> str:
    """
    Return a persistent ICS UID for this visit.

    Legacy pk-only UIDs are replaced once so Google stops merging reseeds into
    old calendar rows. Already-unique UIDs are left alone.
    """
    if not visit.pk:
        raise ValueError('Visit must be saved before assigning ics_uid.')
    if visit.ics_uid and not is_legacy_pk_ics_uid(visit.ics_uid, visit):
        return visit.ics_uid
    visit.ics_uid = default_ics_uid(visit)
    if save:
        visit.save(update_fields=['ics_uid', 'updated_at'])
    return visit.ics_uid


def regenerate_ics_uid(visit: Visit, *, save: bool = True) -> str:
    """Force a new UID (e.g. after a bad Google merge). Resets SEQUENCE to 0."""
    if not visit.pk:
        raise ValueError('Visit must be saved before assigning ics_uid.')
    visit.ics_uid = default_ics_uid(visit)
    visit.ics_sequence = 0
    if save:
        visit.save(update_fields=['ics_uid', 'ics_sequence', 'updated_at'])
    return visit.ics_uid


def resolve_visit_by_manage_token(token: str) -> Visit | None:
    token = (token or '').strip()
    if not token:
        return None
    return (
        Visit.objects.select_related('client', 'business_service', 'series')
        .filter(calendar_manage_token=token)
        .first()
    )


def manage_url_path(visit: Visit, *, create_token: bool = True) -> str:
    if create_token:
        ensure_calendar_manage_token(visit)
    if not visit.calendar_manage_token:
        return ''
    return reverse(
        'operations:booking_manage',
        kwargs={'token': visit.calendar_manage_token},
    )


def manage_url(
    visit: Visit,
    *,
    request=None,
    create_token: bool = True,
    require_absolute: bool = False,
) -> str:
    """
    Public manage URL for a visit.

    Prefer ``request.build_absolute_uri`` when a request is available.
    Otherwise prefix with ``PUBLIC_SITE_URL``. Email bodies must pass
    ``require_absolute=True`` so customers never get a host-less path.
    """
    path = manage_url_path(visit, create_token=create_token)
    if not path:
        return ''
    if request is not None:
        return request.build_absolute_uri(path)
    base = (getattr(settings, 'PUBLIC_SITE_URL', '') or '').strip().rstrip('/')
    if base:
        return f'{base}{path}'
    if require_absolute:
        raise ValueError(
            'PUBLIC_SITE_URL is not set, so booking manage links cannot be absolute. '
            'Set PUBLIC_SITE_URL in .env (e.g. https://your-tunnel.ngrok-free.app or '
            'https://app.dad4dogs.ca), or send the email from a browser request.'
        )
    return path


def absolute_manage_url(visit: Visit, *, request=None, create_token: bool = True) -> str:
    """Absolute manage URL for emails / ICS DESCRIPTION; raises ValueError if impossible."""
    return manage_url(
        visit,
        request=request,
        create_token=create_token,
        require_absolute=True,
    )


def series_siblings_awaiting_confirm(visit: Visit):
    """Other visits in the same series still awaiting initial client confirm."""
    if not visit.series_id:
        return Visit.objects.none()
    return (
        Visit.objects.filter(
            series_id=visit.series_id,
            calendar_invite_state=Visit.CalendarInviteState.AWAITING_CONFIRM,
        )
        .exclude(pk=visit.pk)
        .order_by('scheduled_start')
    )


def mark_awaiting_confirm(visit: Visit, *, save: bool = True) -> None:
    ensure_calendar_manage_token(visit, save=False)
    visit.calendar_invite_state = Visit.CalendarInviteState.AWAITING_CONFIRM
    if save and visit.pk:
        visit.save(
            update_fields=[
                'calendar_manage_token',
                'calendar_invite_state',
                'updated_at',
            ]
        )


def confirm_visit(visit: Visit, *, save: bool = True) -> Visit:
    """Client confirmed times — ready for Email B (ICS). Does not send email."""
    ensure_calendar_manage_token(visit, save=False)
    ensure_ics_uid(visit, save=False)
    visit.calendar_invite_state = Visit.CalendarInviteState.INVITE_ISSUED
    visit.ics_sequence = 0
    if save:
        visit.save(
            update_fields=[
                'calendar_manage_token',
                'ics_uid',
                'ics_sequence',
                'calendar_invite_state',
                'updated_at',
            ]
        )
    return visit


def confirm_series_awaiting(visit: Visit) -> list[Visit]:
    """Confirm this visit and all series siblings still awaiting initial confirm."""
    confirmed = [confirm_visit(visit)]
    for sibling in series_siblings_awaiting_confirm(visit):
        confirmed.append(confirm_visit(sibling))
    return confirmed


def apply_client_reschedule(visit: Visit, *, start, end) -> Visit:
    """Update schedule from the manage page; capacity/overlap via Visit.save()."""
    visit.scheduled_start = start
    visit.scheduled_end = end
    if visit.calendar_invite_state == Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM:
        visit.calendar_invite_state = Visit.CalendarInviteState.INVITE_ISSUED
    visit.save()
    return visit


def approve_staff_change(visit: Visit, *, save: bool = True) -> Visit:
    if visit.calendar_invite_state != Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM:
        return visit
    visit.calendar_invite_state = Visit.CalendarInviteState.INVITE_ISSUED
    if save:
        visit.save(update_fields=['calendar_invite_state', 'updated_at'])
    return visit


def cancel_via_manage(visit: Visit) -> Visit:
    """Client (or approved) cancel — ops status cancelled + invite lifecycle."""
    visit.status = Visit.Status.CANCELLED
    visit.calendar_invite_state = Visit.CalendarInviteState.CANCELLED_INVITE
    visit.save(update_fields=['status', 'calendar_invite_state', 'updated_at'])
    return visit


def calendar_ics_in_play(visit: Visit) -> bool:
    """True when an ICS was issued or a staff change is awaiting client confirm."""
    return visit.calendar_invite_state in {
        Visit.CalendarInviteState.INVITE_ISSUED,
        Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM,
    }


def can_hard_delete_visit(visit: Visit) -> bool:
    """Hard delete only when no outbound ICS exists yet."""
    return visit.calendar_invite_state in {
        Visit.CalendarInviteState.NONE,
        Visit.CalendarInviteState.AWAITING_CONFIRM,
    }


def mark_awaiting_change_confirm(visit: Visit, *, save: bool = True) -> None:
    ensure_calendar_manage_token(visit, save=False)
    visit.calendar_invite_state = Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM
    if save and visit.pk:
        visit.save(
            update_fields=[
                'calendar_manage_token',
                'calendar_invite_state',
                'updated_at',
            ]
        )


def bump_ics_sequence(visit: Visit, *, save: bool = True) -> int:
    visit.ics_sequence = int(visit.ics_sequence or 0) + 1
    if save and visit.pk:
        visit.save(update_fields=['ics_sequence', 'updated_at'])
    return visit.ics_sequence


def soft_cancel_visit(visit: Visit, *, save: bool = True) -> Visit:
    """Cancel in place so UID/SEQUENCE remain for METHOD:CANCEL."""
    visit.status = Visit.Status.CANCELLED
    if save and visit.pk:
        visit.save(update_fields=['status', 'updated_at'])
    return visit


def notify_staff_schedule_change(
    visit: Visit,
    *,
    immediate: bool,
    cancelled: bool,
    request=None,
) -> str:
    """
    After staff edit/cancel of an invited visit.

    Returns a short staff-facing result label: ``email_c``, ``ics_request``,
    or ``ics_cancel``. Caller soft-cancels before calling when ``cancelled``.
    """
    from operations.services.visit_email import (
        send_booking_change_review,
        send_booking_ics_invite,
    )

    if immediate:
        bump_ics_sequence(visit)
        method = 'CANCEL' if cancelled else 'REQUEST'
        if cancelled:
            visit.calendar_invite_state = Visit.CalendarInviteState.CANCELLED_INVITE
            visit.save(update_fields=['calendar_invite_state', 'updated_at'])
        else:
            visit.calendar_invite_state = Visit.CalendarInviteState.INVITE_ISSUED
            visit.save(update_fields=['calendar_invite_state', 'updated_at'])
        send_booking_ics_invite(
            visit.client, [visit], method=method, request=request,
        )
        return 'ics_cancel' if cancelled else 'ics_request'

    send_booking_change_review(
        visit.client, [visit], cancelled=cancelled, request=request,
    )
    return 'email_c'
