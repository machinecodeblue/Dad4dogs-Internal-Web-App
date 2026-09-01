from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from icalendar import Calendar
from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase, override_settings
from django.urls import reverse

from operations.capacity import INSURANCE_CEILING
from operations.forms import VisitForm
from operations.models import (
    BusinessProfile,
    ClientProfile,
    CustomerOwner,
    PendingCalendarEvent,
    Visit,
)
from operations.services.gmail_send import (
    BOOKING_ICS_FILENAME,
    GmailSendError,
    _load_credentials,
    build_booking_invite_message,
    send_gmail,
)
from operations.services.visit_email import (
    VisitEmailError,
    format_booking_confirmation,
    generate_booking_ics,
    send_booking_confirmation,
)
from operations.tests.conftest import TZ


class PendingEventApproveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        self.end = datetime(2026, 3, 10, 17, 0, tzinfo=TZ)

    def test_approve_creates_visit(self):
        event = PendingCalendarEvent.objects.create(
            event_uid='uid-ok',
            summary='Rex boarding',
            start_datetime=self.start,
            end_datetime=self.end,
            matched_client=self.dog,
        )
        response = self.client.post(
            reverse('operations:approve_pending_event', args=[event.pk]),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.review_status, PendingCalendarEvent.ReviewStatus.APPROVED)
        self.assertTrue(
            Visit.objects.filter(client=self.dog, scheduled_start=self.start).exists(),
        )

    def test_approve_capacity_block_keeps_event_pending(self):
        from operations.capacity import count_dogs_on_day
        now = datetime.now(tz=TZ)
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Dog{i}',
                owner_name=f'Owner{i}',
                owner_email=f'cap{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=self.start,
                scheduled_end=self.end,
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)
        event = PendingCalendarEvent.objects.create(
            event_uid='uid-full',
            summary='One more dog',
            start_datetime=self.start,
            end_datetime=self.end,
            matched_client=self.dog,
        )
        response = self.client.post(
            reverse('operations:approve_pending_event', args=[event.pk]),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.review_status, PendingCalendarEvent.ReviewStatus.PENDING)
        self.assertFalse(Visit.objects.filter(client=self.dog).exists())


@override_settings(BOOKING_CLIENT_NOTES_URL='https://dad4dogs.ca/dash/')
class VisitEmailTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        )
        profile = BusinessProfile.load()
        profile.business_name = 'David Lundquist (Dad 4 Dogs)'
        profile.business_email = 'david@machinecodeblue.com'
        profile.address = '191 Grey Street, London, Ontario, N6B 1G2'
        profile.save()

    def test_format_single_visit_confirmation(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            notes='Gate code 1234',
        )
        subject, body = format_booking_confirmation(self.dog, [visit])
        self.assertIn('Winston', subject)
        self.assertIn('Alexa Green', body)
        self.assertIn('Gate code 1234', body)
        self.assertIn('Apr 11, 2026', body)

    @override_settings(PUBLIC_SITE_URL='https://happywaffle.ngrok.app')
    def test_format_confirmation_includes_feed_url_when_public_site_set(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        self.dog.ensure_feed_credentials()
        _, body = format_booking_confirmation(self.dog, [visit])
        self.assertIn('photo feed anytime', body)
        self.assertIn(f'/feed/{self.dog.feed_secret}/winston/', body)
        self.assertIn('https://happywaffle.ngrok.app/feed/', body)

    def test_generate_booking_ics_single_visit(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            notes='Gate code 1234',
        )
        ics_bytes = generate_booking_ics([visit])
        cal = Calendar.from_ical(ics_bytes)
        self.assertEqual(cal.get('method'), 'REQUEST')
        events = [c for c in cal.walk() if c.name == 'VEVENT']
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertIn('visit_', str(event.get('uid')))
        description = str(event.get('description'))
        self.assertIn('Gate code 1234', description)
        self.assertIn('https://dad4dogs.ca/dash/', description)
        self.assertIn('191 Grey Street', str(event.get('location')))
        self.assertEqual(str(event.get('status')), 'CONFIRMED')
        self.assertEqual(int(event.get('sequence')), 0)
        self.assertIn('david@machinecodeblue.com', str(event.get('organizer')))
        attendees = event.get('attendee')
        if not isinstance(attendees, list):
            attendees = [attendees]
        attendee_emails = [str(a) for a in attendees]
        self.assertTrue(any('alexagreen4@outlook.com' in email for email in attendee_emails))
        self.assertTrue(any('david@machinecodeblue.com' in email for email in attendee_emails))
        client_attendee = next(
            a for a in attendees if 'alexagreen4@outlook.com' in str(a)
        )
        self.assertEqual(client_attendee.params.get('RSVP'), 'TRUE')
        self.assertEqual(client_attendee.params.get('PARTSTAT'), 'NEEDS-ACTION')
        organizer = event.get('organizer')
        self.assertEqual(organizer.params.get('CN'), 'David Lundquist (Dad 4 Dogs)')

    def test_generate_booking_ics_requires_business_email(self):
        profile = BusinessProfile.load()
        profile.business_email = ''
        profile.save()
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        with self.assertRaises(VisitEmailError) as ctx:
            generate_booking_ics([visit])
        self.assertIn('Settings', str(ctx.exception))

    def test_generate_booking_ics_repeat_series(self):
        visits = [
            Visit.objects.create(
                client=self.dog,
                scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            ),
            Visit.objects.create(
                client=self.dog,
                scheduled_start=datetime(2026, 4, 18, 13, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 18, 18, 0, tzinfo=TZ),
            ),
        ]
        cal = Calendar.from_ical(generate_booking_ics(visits))
        events = [c for c in cal.walk() if c.name == 'VEVENT']
        self.assertEqual(len(events), 2)

    def test_build_booking_invite_message_layers(self):
        ics_bytes = b'BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nEND:VCALENDAR\r\n'
        message = build_booking_invite_message(
            subject='Test',
            body='Plain body',
            to='client@example.com',
            ics_bytes=ics_bytes,
        )
        self.assertEqual(message.get_content_type(), 'multipart/mixed')
        payloads = list(message.walk())
        content_types = [part.get_content_type() for part in payloads]
        self.assertIn('text/plain', content_types)
        self.assertIn('text/calendar', content_types)
        inline_calendar = next(
            part for part in payloads
            if part.get_content_type() == 'text/calendar'
        )
        self.assertIn('method=REQUEST', inline_calendar['Content-Type'])
        attachment = next(
            part for part in payloads
            if BOOKING_ICS_FILENAME in (part.get('Content-Disposition') or '')
        )
        self.assertIn('attachment', attachment.get('Content-Disposition', ''))

    @patch('operations.services.visit_email.send_gmail_booking_invite')
    def test_send_booking_confirmation_marks_visits(self, mock_send_invite):
        mock_send_invite.return_value = {'id': 'msg-123'}
        visits = [
            Visit.objects.create(
                client=self.dog,
                scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            ),
            Visit.objects.create(
                client=self.dog,
                scheduled_start=datetime(2026, 4, 12, 13, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 12, 18, 0, tzinfo=TZ),
            ),
        ]
        send_booking_confirmation(self.dog, visits)
        mock_send_invite.assert_called_once()
        kwargs = mock_send_invite.call_args.kwargs
        self.assertEqual(kwargs['to'], 'alexagreen4@outlook.com')
        self.assertIn('2 bookings', kwargs['body'])
        self.assertIn('Winston', kwargs['subject'])
        self.assertTrue(kwargs['ics_bytes'].startswith(b'BEGIN:VCALENDAR'))
        for visit in visits:
            visit.refresh_from_db()
            self.assertIsNotNone(visit.confirmation_email_sent_at)

    def test_create_form_includes_email_checkbox(self):
        form = VisitForm(client=self.dog)
        self.assertIn('send_confirmation_email', form.fields)
        self.assertIn('alexagreen4@outlook.com', form.fields['send_confirmation_email'].label)

    def test_edit_form_omits_email_checkbox(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        form = VisitForm(instance=visit)
        self.assertNotIn('send_confirmation_email', form.fields)

    def test_dog_detail_offers_send_email_when_unsent(self):
        CustomerOwner.ensure_for_client(self.dog)
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-email', 'e@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'Send email')
        self.assertContains(
            response,
            reverse('operations:visit_send_confirmation', args=[visit.pk]),
        )
        self.assertNotContains(response, 'emailed')

    def test_dog_detail_shows_emailed_date_when_sent(self):
        CustomerOwner.ensure_for_client(self.dog)
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            confirmation_email_sent_at=datetime(2026, 4, 10, 12, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-emailed', 'e2@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'emailed Apr 10')
        self.assertNotContains(response, 'Send email')

    @patch('operations.views.scheduling.visits.send_booking_confirmation')
    def test_send_confirmation_view_calls_email(self, mock_send):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-send', 'e3@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(
            reverse('operations:visit_send_confirmation', args=[visit.pk]),
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        self.assertEqual(args[0], self.dog)
        self.assertEqual(list(args[1]), [visit])

    @patch('operations.views.scheduling.visits.send_booking_confirmation')
    def test_send_confirmation_view_skips_if_already_sent(self, mock_send):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            confirmation_email_sent_at=datetime(2026, 4, 10, 12, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-skip', 'e4@example.com', 'pass')
        self.client.force_login(user)
        self.client.post(reverse('operations:visit_send_confirmation', args=[visit.pk]))
        mock_send.assert_not_called()


@override_settings(GMAIL_OAUTH_DIR=Path('/nonexistent/oauth-dir'))
class GmailSendTests(TestCase):
    def test_send_gmail_requires_token(self):
        with self.assertRaises(GmailSendError) as ctx:
            send_gmail('Subject', 'Body', 'test@example.com')
        self.assertIn('oauth_setup.py', str(ctx.exception))

    @patch('operations.services.gmail_send._credentials_path')
    @patch('operations.services.gmail_send._token_path')
    @patch('operations.services.gmail_send.Credentials')
    def test_refresh_error_becomes_gmail_send_error(self, mock_creds_cls, mock_token, mock_creds_path):
        from google.auth.exceptions import RefreshError

        mock_token.return_value.exists.return_value = True
        mock_creds_path.return_value.exists.return_value = False
        creds = MagicMock()
        creds.expired = True
        creds.refresh_token = 'rt'
        creds.refresh.side_effect = RefreshError('invalid_grant: Bad Request')
        mock_creds_cls.from_authorized_user_file.return_value = creds
        with self.assertRaises(GmailSendError) as ctx:
            _load_credentials()
        self.assertIn('oauth_setup.py', str(ctx.exception))