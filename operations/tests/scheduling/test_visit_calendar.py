from datetime import datetime, timedelta

from unittest.mock import patch

from django.test import Client as DjangoTestClient, TestCase, override_settings
from django.urls import reverse

from operations.models import ClientProfile, Visit, VisitSeries
from operations.services import visit_calendar
from operations.tests.conftest import TZ, default_service_pk, ready_for_standard_stay


class VisitCalendarHelpersTests(TestCase):
    def setUp(self):
        self.dog = ready_for_standard_stay(
            ClientProfile.objects.create(
                dog_name='Buster',
                owner_name='Pat',
                owner_email='pat@example.com',
            )
        )
        self.start = datetime(2026, 9, 10, 9, 0, tzinfo=TZ)
        self.visit = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            scheduled_start=self.start,
            scheduled_end=self.start + timedelta(hours=8),
        )

    def test_ensure_token_and_resolve(self):
        token = visit_calendar.ensure_calendar_manage_token(self.visit)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.calendar_manage_token, token)
        self.assertEqual(
            visit_calendar.resolve_visit_by_manage_token(token).pk,
            self.visit.pk,
        )
        self.assertIsNone(visit_calendar.resolve_visit_by_manage_token('nope'))

    def test_ensure_ics_uid_stable(self):
        uid = visit_calendar.ensure_ics_uid(self.visit)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.ics_uid, uid)
        self.assertEqual(visit_calendar.ensure_ics_uid(self.visit), uid)
        self.assertIn(f'visit-{self.visit.pk}-', uid)
        self.assertNotEqual(uid, f'visit_{self.visit.pk}@dad4dogs.local')

    def test_legacy_pk_ics_uid_is_upgraded(self):
        legacy = f'visit_{self.visit.pk}@dad4dogs.local'
        self.visit.ics_uid = legacy
        self.visit.save(update_fields=['ics_uid', 'updated_at'])
        with self.settings(ICAL_UID_DOMAIN='dad4dogs.local'):
            uid = visit_calendar.ensure_ics_uid(self.visit)
        self.visit.refresh_from_db()
        self.assertNotEqual(uid, legacy)
        self.assertEqual(self.visit.ics_uid, uid)
        self.assertIn(f'visit-{self.visit.pk}-', uid)

    @override_settings(PUBLIC_SITE_URL='https://app.example.test')
    def test_manage_url_uses_token(self):
        visit_calendar.ensure_calendar_manage_token(self.visit)
        url = visit_calendar.manage_url(self.visit)
        self.assertTrue(
            url.startswith(
                f'https://app.example.test/bookings/manage/{self.visit.calendar_manage_token}/'
            )
        )

    def test_absolute_manage_url_requires_public_site_without_request(self):
        visit_calendar.ensure_calendar_manage_token(self.visit)
        with self.settings(PUBLIC_SITE_URL=''):
            with self.assertRaises(ValueError):
                visit_calendar.absolute_manage_url(self.visit)

    def test_mark_awaiting_confirm_and_series_siblings(self):
        series = VisitSeries.objects.create(
            client=self.dog,
            frequency='daily',
            interval=1,
            end_type='after',
            total_occurrences=2,
            anchor_start=self.start,
            anchor_end=self.start + timedelta(hours=8),
        )
        self.visit.series = series
        self.visit.series_position = 1
        self.visit.save(update_fields=['series', 'series_position', 'updated_at'])
        visit_calendar.mark_awaiting_confirm(self.visit)

        sibling = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            series=series,
            series_position=2,
            scheduled_start=self.start + timedelta(days=1),
            scheduled_end=self.start + timedelta(days=1, hours=8),
        )
        visit_calendar.mark_awaiting_confirm(sibling)

        others = list(visit_calendar.series_siblings_awaiting_confirm(self.visit))
        self.assertEqual([v.pk for v in others], [sibling.pk])

        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.AWAITING_CONFIRM,
        )
        self.assertTrue(self.visit.calendar_manage_token)


class BookingManageViewTests(TestCase):
    def setUp(self):
        self.http = DjangoTestClient()
        self.dog = ready_for_standard_stay(
            ClientProfile.objects.create(
                dog_name='Buster',
                owner_name='Pat',
                owner_email='pat@example.com',
            )
        )
        self.start = datetime(2026, 9, 10, 9, 0, tzinfo=TZ)
        self.visit = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            scheduled_start=self.start,
            scheduled_end=self.start + timedelta(hours=8),
        )
        visit_calendar.mark_awaiting_confirm(self.visit)
        self.visit.refresh_from_db()
        self.url = reverse(
            'operations:booking_manage',
            kwargs={'token': self.visit.calendar_manage_token},
        )

    def test_get_does_not_confirm(self):
        response = self.http.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.AWAITING_CONFIRM,
        )

    @patch('operations.views.scheduling.booking_manage.send_booking_ics_invite')
    def test_post_confirm_flips_state(self, mock_ics):
        mock_ics.return_value = 1
        response = self.http.post(self.url, {'action': 'confirm'})
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.INVITE_ISSUED,
        )
        self.assertEqual(self.visit.ics_sequence, 0)
        self.assertTrue(self.visit.ics_uid)
        mock_ics.assert_called_once()

    @patch('operations.views.scheduling.booking_manage.send_booking_ics_invite')
    def test_confirm_series(self, mock_ics):
        mock_ics.return_value = 2
        series = VisitSeries.objects.create(
            client=self.dog,
            frequency='daily',
            interval=1,
            end_type='after',
            total_occurrences=2,
            anchor_start=self.start,
            anchor_end=self.start + timedelta(hours=8),
        )
        self.visit.series = series
        self.visit.series_position = 1
        self.visit.save(update_fields=['series', 'series_position', 'updated_at'])
        sibling = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            series=series,
            series_position=2,
            scheduled_start=self.start + timedelta(days=1),
            scheduled_end=self.start + timedelta(days=1, hours=8),
        )
        visit_calendar.mark_awaiting_confirm(sibling)

        response = self.http.post(self.url, {'action': 'confirm_series'})
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.INVITE_ISSUED,
        )
        self.assertEqual(
            sibling.calendar_invite_state,
            Visit.CalendarInviteState.INVITE_ISSUED,
        )
        mock_ics.assert_called_once()

    def test_cancel(self):
        response = self.http.post(self.url, {'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, Visit.Status.CANCELLED)
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.CANCELLED_INVITE,
        )

    def test_unknown_token_404(self):
        response = self.http.get(
            reverse('operations:booking_manage', kwargs={'token': 'not-a-real-token'}),
        )
        self.assertEqual(response.status_code, 404)

    @patch('operations.views.scheduling.booking_manage.send_booking_ics_invite')
    def test_approve_staff_cancel_sends_cancel_ics(self, mock_ics):
        mock_ics.return_value = 1
        visit_calendar.confirm_visit(self.visit)
        visit_calendar.soft_cancel_visit(self.visit)
        visit_calendar.mark_awaiting_change_confirm(self.visit)
        self.visit.refresh_from_db()
        response = self.http.post(self.url, {'action': 'approve_change'})
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.CANCELLED_INVITE,
        )
        self.assertEqual(self.visit.ics_sequence, 1)
        mock_ics.assert_called_once()
        self.assertEqual(mock_ics.call_args.kwargs.get('method'), 'CANCEL')


@override_settings(PUBLIC_SITE_URL='https://app.example.test')
class StaffCalendarChangeTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        from operations.models import BusinessProfile

        self.user = get_user_model().objects.create_user(
            username='david-cal',
            password='testpass123',
        )
        self.http = DjangoTestClient()
        self.http.login(username='david-cal', password='testpass123')
        profile = BusinessProfile.load()
        profile.business_email = 'david@dad4dogs.test'
        profile.business_name = 'Dad4dogs'
        profile.save(update_fields=['business_email', 'business_name', 'updated_at'])
        self.dog = ready_for_standard_stay(
            ClientProfile.objects.create(
                dog_name='Buster',
                owner_name='Pat',
                owner_email='pat@example.com',
            )
        )
        self.start = datetime(2026, 9, 10, 9, 0, tzinfo=TZ)
        self.visit = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            scheduled_start=self.start,
            scheduled_end=self.start + timedelta(hours=8),
        )
        visit_calendar.confirm_visit(self.visit)
        self.visit.refresh_from_db()

    def _edit_payload(self, *, immediate=False, start=None, end=None):
        start = start or (self.start + timedelta(hours=1))
        end = end or (start + timedelta(hours=8))
        from operations.services.datetime_parse import format_datetime_input

        data = {
            'start_at': format_datetime_input(start),
            'end_at': format_datetime_input(end),
            'notes': '',
            'business_service': str(self.visit.business_service_id),
        }
        if immediate:
            data['send_calendar_invite_immediately'] = 'on'
        return data

    @patch('operations.services.visit_email.send_gmail')
    @patch('operations.services.visit_email.send_gmail_booking_invite')
    def test_edit_default_sends_email_c(self, mock_ics_send, mock_plain):
        mock_plain.return_value = {'id': '1'}
        response = self.http.post(
            reverse('operations:visit_edit', args=[self.visit.pk]),
            self._edit_payload(immediate=False),
        )
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM,
        )
        self.assertEqual(self.visit.ics_sequence, 0)
        mock_plain.assert_called_once()
        mock_ics_send.assert_not_called()

    @patch('operations.services.visit_email.send_gmail')
    @patch('operations.services.visit_email.send_gmail_booking_invite')
    def test_edit_immediate_bumps_sequence(self, mock_ics_send, mock_plain):
        mock_ics_send.return_value = {'id': '1'}
        response = self.http.post(
            reverse('operations:visit_edit', args=[self.visit.pk]),
            self._edit_payload(immediate=True),
        )
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.INVITE_ISSUED,
        )
        self.assertEqual(self.visit.ics_sequence, 1)
        mock_ics_send.assert_called_once()
        self.assertEqual(mock_ics_send.call_args.kwargs.get('method'), 'REQUEST')
        mock_plain.assert_not_called()

    @patch('operations.services.visit_email.send_gmail')
    @patch('operations.services.visit_email.send_gmail_booking_invite')
    def test_soft_cancel_immediate_sends_cancel(self, mock_ics_send, mock_plain):
        mock_ics_send.return_value = {'id': '1'}
        response = self.http.post(
            reverse('operations:visit_delete', args=[self.visit.pk]),
            {'send_calendar_invite_immediately': '1'},
        )
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, Visit.Status.CANCELLED)
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.CANCELLED_INVITE,
        )
        self.assertEqual(self.visit.ics_sequence, 1)
        mock_ics_send.assert_called_once()
        self.assertEqual(mock_ics_send.call_args.kwargs.get('method'), 'CANCEL')
        mock_plain.assert_not_called()

    @patch('operations.services.visit_email.send_gmail')
    @patch('operations.services.visit_email.send_gmail_booking_invite')
    def test_soft_cancel_default_email_c(self, mock_ics_send, mock_plain):
        mock_plain.return_value = {'id': '1'}
        response = self.http.post(
            reverse('operations:visit_delete', args=[self.visit.pk]),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, Visit.Status.CANCELLED)
        self.assertEqual(
            self.visit.calendar_invite_state,
            Visit.CalendarInviteState.AWAITING_CHANGE_CONFIRM,
        )
        self.assertEqual(self.visit.ics_sequence, 0)
        mock_plain.assert_called_once()
        mock_ics_send.assert_not_called()
    def test_hard_delete_when_never_invited(self):
        plain = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            scheduled_start=self.start + timedelta(days=3),
            scheduled_end=self.start + timedelta(days=3, hours=8),
        )
        pk = plain.pk
        response = self.http.post(reverse('operations:visit_delete', args=[pk]), {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Visit.objects.filter(pk=pk).exists())

    def test_build_invite_message_cancel_method_header(self):
        from operations.services.gmail_send import build_booking_invite_message

        msg = build_booking_invite_message(
            'Subj',
            'Body',
            'pat@example.com',
            b'BEGIN:VCALENDAR\r\nMETHOD:CANCEL\r\nEND:VCALENDAR\r\n',
            method='CANCEL',
        )
        found = False
        for part in msg.walk():
            ctype = part.get('Content-Type', '')
            if 'text/calendar' in ctype and 'method=CANCEL' in ctype:
                found = True
                break
        self.assertTrue(found, msg.as_string())
