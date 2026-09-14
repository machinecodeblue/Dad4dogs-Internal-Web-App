from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client as DjangoTestClient, TestCase, override_settings
from django.urls import reverse

from operations.models import ClientProfile, Visit, VisitSeries
from operations.services import visit_calendar
from operations.services.visit_series_ops import (
    cancel_scheduled_series,
    shift_scheduled_series,
)
from operations.tests.conftest import TZ, default_service_pk, ready_for_standard_stay


@override_settings(PUBLIC_SITE_URL='https://app.example.test')
class VisitSeriesOpsTests(TestCase):
    def setUp(self):
        from operations.models import BusinessProfile

        profile = BusinessProfile.load()
        profile.business_email = 'david@dad4dogs.test'
        profile.save(update_fields=['business_email', 'updated_at'])

        self.dog = ready_for_standard_stay(
            ClientProfile.objects.create(
                dog_name='SeriesDog',
                owner_name='Pat',
                owner_email='pat@example.com',
            )
        )
        self.start = datetime(2026, 10, 5, 9, 0, tzinfo=TZ)  # Monday
        self.series = VisitSeries.objects.create(
            client=self.dog,
            frequency='daily',
            interval=1,
            end_type='after',
            total_occurrences=3,
            anchor_start=self.start,
            anchor_end=self.start + timedelta(hours=8),
        )
        self.visits = []
        for i in range(3):
            self.visits.append(
                Visit.objects.create(
                    client=self.dog,
                    business_service_id=default_service_pk(),
                    series=self.series,
                    series_position=i + 1,
                    scheduled_start=self.start + timedelta(days=i),
                    scheduled_end=self.start + timedelta(days=i, hours=8),
                )
            )
        # Completed fourth member — must stay put
        self.completed = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            series=self.series,
            series_position=4,
            scheduled_start=self.start - timedelta(days=7),
            scheduled_end=self.start - timedelta(days=7) + timedelta(hours=8),
            status=Visit.Status.COMPLETED,
        )

    def test_shift_moves_all_scheduled_leaves_completed(self):
        anchor = self.visits[0]
        prior_start, prior_end = anchor.scheduled_start, anchor.scheduled_end
        new_start = prior_start + timedelta(days=1)
        new_end = prior_end + timedelta(days=1)
        result = shift_scheduled_series(
            anchor,
            prior_start=prior_start,
            prior_end=prior_end,
            new_start=new_start,
            new_end=new_end,
        )
        self.assertEqual(len(result.updated), 3)
        self.assertEqual(result.unchanged_other_statuses, 1)
        for i, visit in enumerate(self.visits):
            visit.refresh_from_db()
            self.assertEqual(
                visit.scheduled_start,
                self.start + timedelta(days=i + 1),
            )
        self.completed.refresh_from_db()
        self.assertEqual(
            self.completed.scheduled_start,
            self.start - timedelta(days=7),
        )

    def test_shift_capacity_block_is_atomic(self):
        # Fill a far day so the shift does not collide with other series members' old days.
        from operations.capacity import INSURANCE_CEILING

        shift_days = 14
        block_day_start = self.start + timedelta(days=shift_days)
        for i in range(INSURANCE_CEILING):
            dog = ready_for_standard_stay(
                ClientProfile.objects.create(
                    dog_name=f'Fill{i}',
                    owner_name=f'O{i}',
                    owner_email=f'fill{i}@example.com',
                )
            )
            Visit.objects.create(
                client=dog,
                business_service_id=default_service_pk(),
                scheduled_start=block_day_start,
                scheduled_end=block_day_start + timedelta(hours=8),
            )
        anchor = self.visits[0]
        with self.assertRaises(ValidationError):
            shift_scheduled_series(
                anchor,
                prior_start=anchor.scheduled_start,
                prior_end=anchor.scheduled_end,
                new_start=anchor.scheduled_start + timedelta(days=shift_days),
                new_end=anchor.scheduled_end + timedelta(days=shift_days),
            )
        for visit in self.visits:
            visit.refresh_from_db()
            self.assertEqual(
                visit.scheduled_start,
                self.start + timedelta(days=visit.series_position - 1),
            )

    def test_cancel_series_scheduled_only(self):
        result = cancel_scheduled_series(self.visits[0])
        self.assertEqual(result.hard_deleted, 3)
        self.assertEqual(result.unchanged_other_statuses, 1)
        self.assertEqual(
            Visit.objects.filter(series=self.series, status=Visit.Status.SCHEDULED).count(),
            0,
        )
        self.assertTrue(Visit.objects.filter(pk=self.completed.pk).exists())

    @patch('operations.services.visit_calendar.notify_staff_schedule_change')
    def test_shift_notifies_invited_visits(self, mock_notify):
        mock_notify.return_value = 'email_c'
        for visit in self.visits:
            visit_calendar.confirm_visit(visit)
        anchor = self.visits[0]
        shift_scheduled_series(
            anchor,
            prior_start=anchor.scheduled_start,
            prior_end=anchor.scheduled_end,
            new_start=anchor.scheduled_start + timedelta(hours=1),
            new_end=anchor.scheduled_end + timedelta(hours=1),
            immediate_calendar=False,
        )
        self.assertEqual(mock_notify.call_count, 3)


@override_settings(PUBLIC_SITE_URL='https://app.example.test')
class VisitSeriesEditViewTests(TestCase):
    def setUp(self):
        from operations.models import BusinessProfile
        from operations.services.datetime_parse import format_datetime_input

        self.format_datetime_input = format_datetime_input
        profile = BusinessProfile.load()
        profile.business_email = 'david@dad4dogs.test'
        profile.save(update_fields=['business_email', 'updated_at'])

        self.user = get_user_model().objects.create_user('david-series', 'd@x.com', 'pass')
        self.http = DjangoTestClient()
        self.http.login(username='david-series', password='pass')
        self.dog = ready_for_standard_stay(
            ClientProfile.objects.create(
                dog_name='ViewDog',
                owner_name='Pat',
                owner_email='pat@example.com',
            )
        )
        self.start = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
        self.series = VisitSeries.objects.create(
            client=self.dog,
            frequency='daily',
            interval=1,
            end_type='after',
            total_occurrences=2,
            anchor_start=self.start,
            anchor_end=self.start + timedelta(hours=8),
        )
        self.v1 = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            series=self.series,
            series_position=1,
            scheduled_start=self.start,
            scheduled_end=self.start + timedelta(hours=8),
        )
        self.v2 = Visit.objects.create(
            client=self.dog,
            business_service_id=default_service_pk(),
            series=self.series,
            series_position=2,
            scheduled_start=self.start + timedelta(days=1),
            scheduled_end=self.start + timedelta(days=1, hours=8),
        )

    def test_edit_page_offers_series_option(self):
        response = self.http.get(reverse('operations:visit_edit', args=[self.v1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'All 2 remaining scheduled visits')

    def test_edit_this_only_leaves_sibling(self):
        new_start = self.start + timedelta(hours=2)
        response = self.http.post(
            reverse('operations:visit_edit', args=[self.v1.pk]),
            {
                'start_at': self.format_datetime_input(new_start),
                'end_at': self.format_datetime_input(new_start + timedelta(hours=8)),
                'notes': '',
                'business_service': str(self.v1.business_service_id),
                'apply_to_series': 'this',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v1.scheduled_start, new_start)
        self.assertEqual(self.v2.scheduled_start, self.start + timedelta(days=1))

    def test_edit_series_shifts_both(self):
        new_start = self.start + timedelta(days=1)
        response = self.http.post(
            reverse('operations:visit_edit', args=[self.v1.pk]),
            {
                'start_at': self.format_datetime_input(new_start),
                'end_at': self.format_datetime_input(new_start + timedelta(hours=8)),
                'notes': '',
                'business_service': str(self.v1.business_service_id),
                'apply_to_series': 'series',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.v1.refresh_from_db()
        self.v2.refresh_from_db()
        self.assertEqual(self.v1.scheduled_start, new_start)
        self.assertEqual(self.v2.scheduled_start, self.start + timedelta(days=2))

    def test_delete_series_removes_both(self):
        response = self.http.post(
            reverse('operations:visit_delete', args=[self.v1.pk]),
            {'apply_to_series': 'series'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Visit.objects.filter(pk=self.v1.pk).exists())
        self.assertFalse(Visit.objects.filter(pk=self.v2.pk).exists())
