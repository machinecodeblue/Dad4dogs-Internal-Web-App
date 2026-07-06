from pathlib import Path

from icalendar import Calendar
from django.utils.dateparse import parse_datetime

from operations.models import ClientProfile, PendingCalendarEvent


def _match_client(text: str) -> ClientProfile | None:
    text_lower = text.lower()
    for client in ClientProfile.objects.all():
        if client.dog_name.lower() in text_lower:
            return client
        if client.owner_email.lower() in text_lower:
            return client
    return None


def parse_ics_file(file_path: Path) -> list[PendingCalendarEvent]:
    """
    Parse an inbound Google Calendar .ics export and create pending checkout visits.
    Matches clients via dog name or owner email in event text.
    """
    content = file_path.read_bytes()
    cal = Calendar.from_ical(content)
    created = []

    for component in cal.walk():
        if component.name != 'VEVENT':
            continue

        uid = str(component.get('uid', ''))
        if not uid or PendingCalendarEvent.objects.filter(event_uid=uid).exists():
            continue

        summary = str(component.get('summary', ''))
        description = str(component.get('description', ''))
        start = component.get('dtstart').dt
        end = component.get('dtend').dt

        if hasattr(start, 'hour'):
            start_dt = start
            end_dt = end
        else:
            from datetime import datetime, time
            from django.utils import timezone as tz
            start_dt = tz.make_aware(datetime.combine(start, time.min))
            end_dt = tz.make_aware(datetime.combine(end, time.min))

        search_text = f'{summary} {description}'
        client = _match_client(search_text)

        event = PendingCalendarEvent.objects.create(
            event_uid=uid,
            summary=summary,
            description=description,
            start_datetime=start_dt,
            end_datetime=end_dt,
            matched_client=client,
        )
        created.append(event)

    return created