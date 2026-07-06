from icalendar import Calendar, Event
from django.http import HttpResponse
from django.utils import timezone

from operations.models import Visit


def generate_ical_feed() -> HttpResponse:
    cal = Calendar()
    cal.add('prodid', '-//Dad4dogs//Internal App//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('X-WR-CALNAME', 'Dad4dogs Bookings')

    visits = Visit.objects.filter(
        status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN],
    ).select_related('client')

    for visit in visits:
        event = Event()
        event.add('uid', f'dad4dogs-visit-{visit.pk}@dad4dogs.local')
        event.add('dtstamp', timezone.now())
        event.add('dtstart', visit.scheduled_start)
        event.add('dtend', visit.scheduled_end)
        event.add(
            'summary',
            f'{visit.client.dog_name} — {visit.client.owner_name}',
        )
        event.add(
            'description',
            f'Dog: {visit.client.dog_name}\n'
            f'Owner: {visit.client.owner_name}\n'
            f'Email: {visit.client.owner_email}',
        )
        cal.add_component(event)

    response = HttpResponse(cal.to_ical(), content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="dad4dogs.ics"'
    return response