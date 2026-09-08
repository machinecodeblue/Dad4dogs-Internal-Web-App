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

    @override_settings(PUBLIC_SITE_URL='https://app.example.test')
    def test_manage_url_uses_token(self):
        visit_calendar.ensure_calendar_manage_token(self.visit)
        url = visit_calendar.manage_url(self.visit)
        self.assertTrue(
            url.startswith(
                f'https://app.example.test/bookings/manage/{self.visit.calendar_manage_token}/'
            )
        )

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
