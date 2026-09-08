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
    domain = getattr(settings, 'ICAL_UID_DOMAIN', 'dad4dogs.local')
    return f'visit_{visit.pk}@{domain}'


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
    if visit.ics_uid:
        return visit.ics_uid
    if not visit.pk:
        raise ValueError('Visit must be saved before assigning ics_uid.')
    visit.ics_uid = default_ics_uid(visit)
    if save:
        visit.save(update_fields=['ics_uid', 'updated_at'])
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


def manage_url(visit: Visit, *, request=None, create_token: bool = True) -> str:
    path = manage_url_path(visit, create_token=create_token)
    if not path:
        return ''
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, 'PUBLIC_SITE_URL', '').rstrip('/')
    return f'{base}{path}' if base else path


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
