from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from operations.capacity import (
    INSURANCE_CEILING,
    as_local,
    capacity_span_dates,
    check_visit_capacity,
    count_dogs_on_day,
    day_bounds,
)
from operations.models import (
    BusinessService,
    CapacitySettings,
    ClientProfile,
    Visit,
)
from operations.tests.conftest import TZ


class VisitCapacitySaveTests(TestCase):
    def setUp(self):
        self.start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        self.end = datetime(2026, 3, 10, 17, 0, tzinfo=TZ)
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )

    def _visit(self, dog=None, **kwargs):
        defaults = {
            'client': dog or self.dog,
            'scheduled_start': self.start,
            'scheduled_end': self.end,
        }
        defaults.update(kwargs)
        return Visit.objects.create(**defaults)

    def _fill_day_over_ceiling(self):
        now = timezone.now()
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Dog{i}',
                owner_name=f'Owner{i}',
                owner_email=f'owner{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=self.start,
                scheduled_end=self.end,
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)

    def test_booking_over_ceiling_is_blocked(self):
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Booked{i}',
                owner_name=f'Owner{i}',
                owner_email=f'booked{i}@example.com',
            )
            Visit.objects.create(
                client=dog,
                scheduled_start=self.start,
                scheduled_end=self.end,
            )
        with self.assertRaises(ValidationError):
            self._visit()

    def test_settings_ceiling_blocks_below_default(self):
        caps = CapacitySettings.load()
        caps.standard_capacity = 2
        caps.insurance_ceiling = 2
        caps.save(update_fields=['standard_capacity', 'insurance_ceiling', 'updated_at'])
        for i in range(2):
            dog = ClientProfile.objects.create(
                dog_name=f'Low{i}',
                owner_name=f'Owner{i}',
                owner_email=f'low{i}@example.com',
            )
            Visit.objects.create(
                client=dog,
                scheduled_start=self.start,
                scheduled_end=self.end,
            )
        with self.assertRaises(ValidationError):
            self._visit()

    def test_check_out_succeeds_when_day_is_over_capacity(self):
        visit = self._visit(
            status=Visit.Status.CHECKED_IN,
            actual_arrival=self.start,
        )
        self._fill_day_over_ceiling()
        visit.check_out()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertIsNotNone(visit.actual_departure)
        self.assertIsNotNone(visit.calculated_fee)

    def test_check_in_succeeds_when_day_is_over_capacity(self):
        visit = self._visit()
        self._fill_day_over_ceiling()
        visit.check_in()
        visit.refresh_from_db()
        self.assertEqual(visit.status, Visit.Status.CHECKED_IN)
        self.assertIsNotNone(visit.actual_arrival)

    def test_reschedule_still_checks_capacity(self):
        visit = self._visit()
        self._fill_day_over_ceiling()
        visit.scheduled_end = datetime(2026, 3, 10, 18, 0, tzinfo=TZ)
        with self.assertRaises(ValidationError):
            visit.save()

    def test_schedule_update_fields_still_checks_capacity(self):
        visit = self._visit()
        self._fill_day_over_ceiling()
        visit.scheduled_end = datetime(2026, 3, 10, 18, 0, tzinfo=TZ)
        with self.assertRaises(ValidationError):
            visit.save(update_fields=['scheduled_end', 'updated_at'])


class CapacityTimezoneTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )

    def test_day_bounds_use_django_timezone(self):
        start, end = day_bounds(date(2026, 4, 10))
        self.assertEqual(getattr(start.tzinfo, 'key', str(start.tzinfo)), 'America/Toronto')
        self.assertEqual(end - start, timedelta(days=1))

    def test_count_include_client_when_absent(self):
        self.assertEqual(
            count_dogs_on_day(date(2026, 5, 1), include_client_id=self.dog.pk),
            1,
        )

    def test_count_include_client_does_not_double_count(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 5, 1, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 5, 1, 17, 0, tzinfo=TZ),
        )
        self.assertEqual(
            count_dogs_on_day(date(2026, 5, 1), include_client_id=self.dog.pk),
            1,
        )

    def test_overnight_counts_on_both_local_calendar_days(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 20, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
        )
        self.assertEqual(count_dogs_on_day(date(2026, 4, 10)), 1)
        self.assertEqual(count_dogs_on_day(date(2026, 4, 11)), 1)
        self.assertEqual(count_dogs_on_day(date(2026, 4, 9)), 0)

    def test_meet_greet_does_not_count_toward_facility_capacity(self):
        from operations.services.context_tenant import get_active_workspace
        from operations.services.pipeline import INITIAL_EVALUATION_SLUG, MEET_GREET_SLUG

        workspace = get_active_workspace()
        meet = BusinessService.objects.get(tenant=workspace, slug=MEET_GREET_SLUG)
        evaluation = BusinessService.objects.get(tenant=workspace, slug=INITIAL_EVALUATION_SLUG)
        self.assertTrue(meet.capacity_exempt)
        self.assertFalse(evaluation.capacity_exempt)

        Visit.objects.create(
            client=self.dog,
            business_service=meet,
            scheduled_start=datetime(2026, 6, 1, 10, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 6, 1, 10, 15, tzinfo=TZ),
        )
        self.assertEqual(count_dogs_on_day(date(2026, 6, 1)), 0)

        other = ClientProfile.objects.create(
            dog_name='EvalDog',
            owner_name='Eval Owner',
            owner_email='eval-cap@example.com',
        )
        Visit.objects.create(
            client=other,
            business_service=evaluation,
            scheduled_start=datetime(2026, 6, 1, 10, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 6, 1, 14, 0, tzinfo=TZ),
        )
        self.assertEqual(count_dogs_on_day(date(2026, 6, 1)), 1)

    def test_naive_datetimes_do_not_crash_capacity(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0),
            scheduled_end=datetime(2026, 4, 11, 17, 0),
        )
        start_day, end_day = capacity_span_dates(visit)
        self.assertEqual(start_day, date(2026, 4, 11))
        self.assertEqual(end_day, date(2026, 4, 11))
        result = check_visit_capacity(visit)
        self.assertEqual(result['status'], 'ok')

    def test_check_visit_capacity_uses_local_span(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 20, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
        )
        result = check_visit_capacity(visit)
        self.assertEqual(result['status'], 'ok')

    def test_exact_midnight_end_belongs_to_prior_day(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 12, 0, 0, tzinfo=TZ),
        )
        start_day, end_day = capacity_span_dates(visit)
        self.assertEqual(start_day, date(2026, 4, 11))
        self.assertEqual(end_day, date(2026, 4, 11))

    def test_end_just_after_midnight_includes_next_day(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 12, 0, 1, tzinfo=TZ),
        )
        _, end_day = capacity_span_dates(visit)
        self.assertEqual(end_day, date(2026, 4, 12))

    def test_midnight_end_not_blocked_by_following_day_ceiling(self):
        now = timezone.now()
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Cap{i}',
                owner_name=f'Owner{i}',
                owner_email=f'midnight{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=datetime(2026, 4, 12, 9, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 12, 17, 0, tzinfo=TZ),
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)
        probe = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 12, 0, 0, tzinfo=TZ),
        )
        result = check_visit_capacity(probe)
        self.assertNotEqual(result['status'], 'blocked')

    def test_multi_day_capacity_uses_one_query(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 1, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 15, 17, 0, tzinfo=TZ),
        )
        with self.assertNumQueries(2):
            check_visit_capacity(visit)

    def test_multi_day_blocks_when_one_day_is_full(self):
        now = timezone.now()
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Span{i}',
                owner_name=f'Owner{i}',
                owner_email=f'span{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
                scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)
        probe = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 1, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 15, 17, 0, tzinfo=TZ),
        )
        result = check_visit_capacity(probe)
        self.assertEqual(result['status'], 'blocked')