from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.models import ClientProfile, CustomerOwner, Visit
from operations.tests.conftest import TZ


class VisitCheckOutTests(TestCase):
    def setUp(self):
        self.owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )

    @patch('operations.models.scheduling.visits.timezone.now')
    def test_check_out_persists_fee_breakdown(self, mock_now):
        arrival = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        departure = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        mock_now.return_value = departure
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=arrival,
            scheduled_end=departure,
            status=Visit.Status.CHECKED_IN,
            actual_arrival=arrival,
        )
        visit.check_out()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertEqual(visit.actual_departure, departure)
        self.assertEqual(visit.calculated_fee, Decimal('15.00'))
        self.assertEqual(visit.fee_breakdown, [{'tier': 'Short Visit', 'amount': '15.00'}])

    def _make_visit(self, **kwargs):
        start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        defaults = {
            'client': self.dog,
            'scheduled_start': start,
            'scheduled_end': end,
        }
        defaults.update(kwargs)
        return Visit.objects.create(**defaults)

    def test_check_in_from_scheduled(self):
        visit = self._make_visit()
        visit.check_in()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertIsNotNone(visit.actual_arrival)

    def test_check_in_rejected_when_already_checked_in(self):
        arrival = datetime(2026, 3, 10, 9, 5, tzinfo=TZ)
        visit = self._make_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=arrival,
        )
        with self.assertRaises(ValidationError) as ctx:
            visit.check_in()
        self.assertIn('scheduled', str(ctx.exception).lower())
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertEqual(visit.actual_arrival, arrival)

    def test_check_in_rejected_when_completed(self):
        visit = self._make_visit(
            status=Visit.Status.COMPLETED,
            actual_arrival=datetime(2026, 3, 10, 9, 5, tzinfo=TZ),
            actual_departure=datetime(2026, 3, 10, 12, 0, tzinfo=TZ),
            calculated_fee=Decimal('15.00'),
        )
        with self.assertRaises(ValidationError):
            visit.check_in()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.COMPLETED)

    def test_check_in_rejected_when_cancelled(self):
        visit = self._make_visit(status=Visit.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            visit.check_in()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CANCELLED)
        self.assertIsNone(visit.actual_arrival)

    def test_check_out_rejected_when_scheduled(self):
        visit = self._make_visit()
        with self.assertRaises(ValidationError) as ctx:
            visit.check_out()
        self.assertIn('checked-in', str(ctx.exception).lower())
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.SCHEDULED)
        self.assertIsNone(visit.actual_departure)
        self.assertIsNone(visit.calculated_fee)

    def test_check_out_rejected_when_already_completed(self):
        arrival = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        departure = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        visit = self._make_visit(
            status=Visit.Status.COMPLETED,
            actual_arrival=arrival,
            actual_departure=departure,
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Short Visit', 'amount': '15.00'}],
        )
        with self.assertRaises(ValidationError):
            visit.check_out()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertEqual(visit.actual_departure, departure)
        self.assertEqual(visit.calculated_fee, Decimal('15.00'))

    def test_stale_instance_does_not_recompute_fee(self):
        arrival = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        visit = self._make_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=arrival,
        )
        stale = Visit.objects.get(pk=visit.pk)
        visit.check_out()
        visit.refresh_from_db()
        first_fee = visit.calculated_fee
        first_departure = visit.actual_departure
        first_breakdown = visit.fee_breakdown

        with patch('operations.pricing.calculate_fee') as mock_fee:
            with self.assertRaises(ValidationError) as ctx:
                stale.check_out()
            mock_fee.assert_not_called()
        self.assertIn('already', str(ctx.exception).lower())

        stale.refresh_from_db()
        self.assertEqual(stale.status, Visit.Status.COMPLETED)
        self.assertEqual(stale.calculated_fee, first_fee)
        self.assertEqual(stale.actual_departure, first_departure)
        self.assertEqual(stale.fee_breakdown, first_breakdown)

    def test_checked_in_with_existing_fee_does_not_overwrite(self):
        arrival = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        visit = self._make_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=arrival,
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Short Visit', 'amount': '15.00'}],
        )
        with patch('operations.pricing.calculate_fee') as mock_fee:
            with self.assertRaises(ValidationError):
                visit.check_out()
            mock_fee.assert_not_called()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertEqual(visit.calculated_fee, Decimal('15.00'))
        self.assertIsNone(visit.actual_departure)

    def test_update_actual_times_checked_in_arrival(self):
        late_tap = datetime(2026, 3, 10, 9, 40, tzinfo=TZ)
        true_arrival = datetime(2026, 3, 10, 9, 5, tzinfo=TZ)
        visit = self._make_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=late_tap,
        )
        visit.update_actual_times(arrival=true_arrival)
        visit.refresh_from_db()
        self.assertEqual(visit.actual_arrival, true_arrival)
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertIsNone(visit.actual_departure)

    def test_update_actual_times_checked_in_rejects_departure(self):
        visit = self._make_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 3, 10, 9, 5, tzinfo=TZ),
        )
        with self.assertRaises(ValidationError):
            visit.update_actual_times(
                arrival=datetime(2026, 3, 10, 9, 0, tzinfo=TZ),
                departure=datetime(2026, 3, 10, 12, 0, tzinfo=TZ),
            )

    def test_update_actual_times_completed_recalculates_fee(self):
        visit = self._make_visit(
            status=Visit.Status.COMPLETED,
            actual_arrival=datetime(2026, 3, 10, 9, 0, tzinfo=TZ),
            actual_departure=datetime(2026, 3, 10, 12, 0, tzinfo=TZ),
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Short Visit', 'amount': '15.00'}],
        )
        visit.update_actual_times(
            arrival=datetime(2026, 3, 10, 8, 0, tzinfo=TZ),
            departure=datetime(2026, 3, 10, 17, 0, tzinfo=TZ),
        )
        visit.refresh_from_db()
        self.assertEqual(visit.actual_arrival, datetime(2026, 3, 10, 8, 0, tzinfo=TZ))
        self.assertEqual(visit.actual_departure, datetime(2026, 3, 10, 17, 0, tzinfo=TZ))
        self.assertEqual(visit.calculated_fee, Decimal('25.00'))
        self.assertEqual(visit.fee_breakdown, [{'tier': 'Daytime Visit', 'amount': '25.00'}])
        self.assertEqual(visit.status, Visit.Status.COMPLETED)

    def test_update_actual_times_rejects_scheduled(self):
        visit = self._make_visit()
        with self.assertRaises(ValidationError):
            visit.update_actual_times(arrival=datetime(2026, 3, 10, 9, 0, tzinfo=TZ))


class VisitCheckInOutViewTests(TestCase):
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

    def _today_visit(self, **kwargs):
        today = timezone.localdate()
        start = datetime(today.year, today.month, today.day, 9, 0, tzinfo=TZ)
        end = datetime(today.year, today.month, today.day, 17, 0, tzinfo=TZ)
        defaults = {
            'client': self.dog,
            'scheduled_start': start,
            'scheduled_end': end,
        }
        defaults.update(kwargs)
        return Visit.objects.create(**defaults)

    def test_double_check_in_does_not_overwrite_arrival(self):
        visit = self._today_visit()
        url = reverse('operations:visit_check_in', args=[visit.pk])
        first = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        visit.refresh_from_db()
        first_arrival = visit.actual_arrival
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertIsNotNone(first_arrival)

        second = self.client.post(url)
        self.assertEqual(second.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertEqual(visit.actual_arrival, first_arrival)

    def test_double_check_out_does_not_rerun_pricing(self):
        arrival = timezone.now()
        visit = self._today_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=arrival,
        )
        url = reverse('operations:visit_check_out', args=[visit.pk])
        first = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        visit.refresh_from_db()
        first_departure = visit.actual_departure
        first_fee = visit.calculated_fee
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertIsNotNone(first_departure)

        second = self.client.post(url)
        self.assertEqual(second.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertEqual(visit.actual_departure, first_departure)
        self.assertEqual(visit.calculated_fee, first_fee)

    @patch('operations.views.scheduling.checkin.timezone.localdate', return_value=date(2026, 4, 10))
    def test_overnight_visit_appears_on_checkin(self, _mock_today):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 20, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
            status=Visit.Status.SCHEDULED,
        )
        response = self.client.get(reverse('operations:mobile_checkin'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rex')

    @patch('operations.services.timeline_visits.timezone.localdate', return_value=date(2026, 4, 10))
    def test_overnight_checked_in_is_timeline_eligible(self, _mock_today):
        from operations.services.timeline_visits import active_checked_in_visits

        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 20, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 4, 10, 20, 5, tzinfo=TZ),
        )
        self.assertEqual(active_checked_in_visits().count(), 1)

    def test_update_arrival_from_checkin(self):
        today = timezone.localdate()
        late = datetime(today.year, today.month, today.day, 9, 40, tzinfo=TZ)
        true_arrival = datetime(today.year, today.month, today.day, 9, 5, tzinfo=TZ)
        visit = self._today_visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=late,
        )
        response = self.client.post(
            reverse('operations:visit_update_actual_times', args=[visit.pk]),
            {'actual_arrival': true_arrival.strftime('%Y-%m-%dT%H:%M')},
        )
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(timezone.localtime(visit.actual_arrival), true_arrival)

    def test_update_completed_times_recalculates_fee_from_checkin(self):
        today = timezone.localdate()
        arrival = datetime(today.year, today.month, today.day, 9, 0, tzinfo=TZ)
        old_departure = datetime(today.year, today.month, today.day, 12, 0, tzinfo=TZ)
        new_departure = datetime(today.year, today.month, today.day, 17, 0, tzinfo=TZ)
        visit = self._today_visit(
            status=Visit.Status.COMPLETED,
            actual_arrival=arrival,
            actual_departure=old_departure,
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Short Visit', 'amount': '15.00'}],
        )
        response = self.client.get(reverse('operations:mobile_checkin'))
        self.assertContains(response, 'Checked out today')
        self.assertContains(response, 'Rex')

        response = self.client.post(
            reverse('operations:visit_update_actual_times', args=[visit.pk]),
            {
                'actual_arrival': arrival.strftime('%Y-%m-%dT%H:%M'),
                'actual_departure': new_departure.strftime('%Y-%m-%dT%H:%M'),
            },
        )
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(timezone.localtime(visit.actual_departure), new_departure)
        self.assertEqual(visit.calculated_fee, Decimal('25.00'))