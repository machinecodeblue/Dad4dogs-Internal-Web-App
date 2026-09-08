from icalendar import Calendar, Event, vCalAddress, vText

from django.conf import settings
from django.utils import timezone

from operations.models import BusinessProfile, ClientProfile, Visit
from operations.services import visit_calendar
from operations.services.gmail_send import (
    GmailSendError,
    send_gmail,
    send_gmail_booking_invite,
)


class VisitEmailError(Exception):
    """Raised when a booking confirmation email cannot be sent."""


def _calendar_invite_profile() -> BusinessProfile:
    """Business Settings (/settings/) — authoritative source for iCal organizer and location."""
    return BusinessProfile.load()


def _event_description(visit: Visit, notes_url: str) -> str:
    dog_name = visit.client.dog_name
    owner_name = visit.client.owner_name
    lines = [
        f'Dog: {dog_name}',
        f'Owner: {owner_name}',
    ]
    manage = visit_calendar.manage_url(visit)
    if manage:
        lines.append(f'To reschedule or cancel, visit: {manage}')
    if notes_url:
        lines.append(f'Contemporaneous notes tracking link: {notes_url}')
    if visit.notes.strip():
        lines.append(visit.notes.strip())
    return '\n'.join(lines)


def _add_organizer(event: Event, email: str, common_name: str) -> None:
    organizer = vCalAddress(f'MAILTO:{email}')
    organizer.params['cn'] = vText(common_name)
    event.add('organizer', organizer, encode=0)


def _add_attendee(
    event: Event,
    *,
    email: str,
    common_name: str,
    rsvp: bool,
    partstat: str = 'NEEDS-ACTION',
) -> None:
    attendee = vCalAddress(f'MAILTO:{email}')
    attendee.params['cn'] = vText(common_name)
    attendee.params['role'] = vText('REQ-PARTICIPANT')
    attendee.params['rsvp'] = vText('TRUE' if rsvp else 'FALSE')
    if rsvp:
        attendee.params['partstat'] = vText(partstat)
    event.add('attendee', attendee, encode=0)


def format_booking_review(client: ClientProfile, visits: list[Visit]) -> tuple[str, str]:
    """Email A — review & confirm link only (no ICS)."""
    if not visits:
        raise VisitEmailError('No visits to review.')

    visits = sorted(visits, key=lambda v: v.scheduled_start)
    for visit in visits:
        visit_calendar.ensure_calendar_manage_token(visit)

    if len(visits) == 1:
        schedule_lines = [f'  {visits[0].schedule_display}']
        manage_lines = [f'  {visit_calendar.manage_url(visits[0])}']
        subject = f'Confirm {client.dog_name}\'s booking with Dad4dogs'
    else:
        schedule_lines = [f'  {visit.schedule_display}' for visit in visits]
        manage_lines = [
            f'  {visit.schedule_display}: {visit_calendar.manage_url(visit)}'
            for visit in visits
        ]
        subject = f'Confirm {client.dog_name}\'s bookings with Dad4dogs ({len(visits)})'

    body_lines = [
        f'Hi {client.owner_name},',
        '',
        f'Please review the proposed booking for {client.dog_name} at Dad4dogs.',
        '',
        'Proposed times:',
        *schedule_lines,
        '',
        'Open this secure link to confirm (or adjust) the booking.',
        'Confirming on the web page is required before a calendar invite is emailed.',
        '',
        *manage_lines,
        '',
        'Thank you,',
        'David — Dad4dogs',
    ]
    return subject, '\n'.join(body_lines)


def format_booking_confirmation(client: ClientProfile, visits: list[Visit]) -> tuple[str, str]:
    """Email B — body after client confirm, accompanying ICS."""
    if not visits:
        raise VisitEmailError('No visits to confirm.')

    visits = sorted(visits, key=lambda v: v.scheduled_start)
    if len(visits) == 1:
        schedule_lines = [f'  {visits[0].schedule_display}']
        schedule_heading = 'Your booking:'
        manage_lines = [f'  {visit_calendar.manage_url(visits[0])}']
    else:
        schedule_heading = f'Your {len(visits)} bookings:'
        schedule_lines = [f'  {visit.schedule_display}' for visit in visits]
        manage_lines = [
            f'  {visit.schedule_display}: {visit_calendar.manage_url(visit)}'
            for visit in visits
        ]

    body_lines = [
        f'Hi {client.owner_name},',
        '',
        f'This confirms boarding for {client.dog_name} at Dad4dogs.',
        '',
        schedule_heading,
        *schedule_lines,
        '',
        'Add these dates to your calendar using the invite in this email,',
        'or open the attached dad4dogs_booking.ics file.',
        '',
        'Manage or cancel anytime:',
        *manage_lines,
    ]

    notes = visits[0].notes.strip()
    if notes:
        body_lines.extend(['', f'Notes: {notes}'])

    client.ensure_feed_credentials()
    feed_url = client.feed_url()
    if feed_url.startswith('http'):
        body_lines.extend([
            '',
            f"Watch {client.dog_name}'s photo feed anytime (bookmark for later):",
            f'  {feed_url}',
        ])

    body_lines.extend([
        '',
        'Thank you,',
        'David — Dad4dogs',
    ])

    if len(visits) == 1:
        subject = f'Dad4dogs booking confirmation — {client.dog_name}'
    else:
        subject = f'Dad4dogs booking confirmation — {client.dog_name} ({len(visits)} visits)'

    return subject, '\n'.join(body_lines)


def generate_booking_ics(visits: list[Visit], *, method: str = 'REQUEST') -> bytes:
    """
    Build an iCalendar REQUEST or CANCEL payload for one or more visits.

    Repeat series: all VEVENT blocks live in one .ics so the customer can import once.
    """
    if not visits:
        raise VisitEmailError('No visits to include in calendar invite.')

    method = (method or 'REQUEST').upper()
    if method not in {'REQUEST', 'CANCEL'}:
        raise VisitEmailError(f'Unsupported calendar METHOD: {method}')

    client_email = (visits[0].client.owner_email or '').strip()
    if not client_email:
        raise VisitEmailError('This customer has no email address on file.')

    profile = _calendar_invite_profile()
    organizer_email = profile.calendar_organizer_email
    if not organizer_email:
        raise VisitEmailError(
            'Business email is not set. Open Settings and save your business email '
            'before sending calendar invites.',
        )

    organizer_cn = profile.calendar_organizer_name
    location = profile.calendar_location
    notes_url = (getattr(settings, 'BOOKING_CLIENT_NOTES_URL', '') or '').strip()

    cal = Calendar()
    cal.add('prodid', '-//Dad4dogs Booking System//dad4dogs.ca//')
    cal.add('version', '2.0')
    cal.add('method', method)

    now = timezone.now()
    for visit in sorted(visits, key=lambda v: v.scheduled_start):
        visit_calendar.ensure_calendar_manage_token(visit, save=True)
        uid = visit_calendar.ensure_ics_uid(visit, save=True)
        dog_name = visit.client.dog_name
        owner_name = visit.client.owner_name

        event = Event()
        event.add('uid', uid)
        event.add('dtstamp', now)
        event.add('dtstart', visit.scheduled_start)
        event.add('dtend', visit.scheduled_end)
        if method == 'CANCEL':
            event.add('summary', f'Dad4dogs Stay: {dog_name} (CANCELLED)')
            event.add('status', 'CANCELLED')
        else:
            event.add('summary', f'Dad4dogs Stay: {dog_name}')
            event.add('description', _event_description(visit, notes_url))
            event.add('status', 'CONFIRMED')
        event.add('sequence', int(visit.ics_sequence or 0))

        if location and method != 'CANCEL':
            event.add('location', location)

        _add_organizer(event, organizer_email, organizer_cn)
        _add_attendee(
            event,
            email=client_email,
            common_name=owner_name,
            rsvp=method == 'REQUEST',
            partstat='ACCEPTED' if method == 'REQUEST' else 'NEEDS-ACTION',
        )
        _add_attendee(
            event,
            email=organizer_email,
            common_name=organizer_cn,
            rsvp=False,
        )

        cal.add_component(event)

    return cal.to_ical()


def send_booking_review_link(client: ClientProfile, visits: list[Visit]) -> int:
    """Email A — plain review link; marks visits awaiting_confirm."""
    recipient = (client.owner_email or '').strip()
    if not recipient:
        raise VisitEmailError('This customer has no email address on file.')

    visits = list(visits)
    if not visits:
        raise VisitEmailError('No visits to review.')

    for visit in visits:
        visit_calendar.mark_awaiting_confirm(visit)

    subject, body = format_booking_review(client, visits)
    try:
        send_gmail(subject=subject, body=body, to=recipient)
    except GmailSendError as exc:
        raise VisitEmailError(str(exc)) from exc

    now = timezone.now()
    visit_ids = [visit.pk for visit in visits]
    Visit.objects.filter(pk__in=visit_ids).update(
        calendar_review_sent_at=now,
        updated_at=now,
    )
    for visit in visits:
        visit.calendar_review_sent_at = now
        visit.calendar_invite_state = Visit.CalendarInviteState.AWAITING_CONFIRM

    return len(visits)


def send_booking_ics_invite(
    client: ClientProfile,
    visits: list[Visit],
    *,
    method: str = 'REQUEST',
) -> int:
    """Email B / B′ — ICS REQUEST or CANCEL using each visit’s ics_sequence."""
    recipient = (client.owner_email or '').strip()
    if not recipient:
        raise VisitEmailError('This customer has no email address on file.')

    visits = list(visits)
    if not visits:
        raise VisitEmailError('No visits to include in calendar invite.')

    subject, body = format_booking_confirmation(client, visits)
    if method.upper() == 'CANCEL':
        subject = f'Dad4dogs booking cancelled — {client.dog_name}'
        body = (
            f'Hi {client.owner_name},\n\n'
            f'The booking for {client.dog_name} has been cancelled.\n'
            'Your calendar should remove the event when you accept this update.\n\n'
            'Thank you,\nDavid — Dad4dogs'
        )

    ics_bytes = generate_booking_ics(visits, method=method)
    try:
        send_gmail_booking_invite(
            subject=subject,
            body=body,
            to=recipient,
            ics_bytes=ics_bytes,
        )
    except GmailSendError as exc:
        raise VisitEmailError(str(exc)) from exc

    now = timezone.now()
    visit_ids = [visit.pk for visit in visits]
    Visit.objects.filter(pk__in=visit_ids).update(
        calendar_invite_sent_at=now,
        confirmation_email_sent_at=now,
        updated_at=now,
    )
    for visit in visits:
        visit.calendar_invite_sent_at = now
        visit.confirmation_email_sent_at = now

    return len(visits)


def send_booking_confirmation(client: ClientProfile, visits: list[Visit]) -> int:
    """
    Legacy name — now sends Email A (review link), not ICS.

    Prefer ``send_booking_review_link`` / ``send_booking_ics_invite`` at new call sites.
    """
    return send_booking_review_link(client, visits)