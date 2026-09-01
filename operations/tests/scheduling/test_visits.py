from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from operations.capacity import INSURANCE_CEILING
from operations.forms import VisitForm
from operations.models import (
    ClientProfile,
    CustomerOwner,
    Visit,
    VisitSeries,
)
from operations.services.visit_repeat import (
    END_AFTER,
    END_ON,
    FREQUENCY_DAILY,
    MAX_OCCURRENCES,
    generate_repeat_occurrences,
    parse_repeat_ends,
)
from operations.tests.conftest import (
    TZ,
    default_service_pk,
    ready_for_standard_stay,
)


class VisitRepeatTests(TestCase):
    def test_parse_repeat_ends_number(self):
        start = datetime(2026, 4, 10, 9, 0, tzinfo=TZ)
        end_type, count, until = parse_repeat_ends('5', start)
        self.assertEqual(end_type, END_AFTER)
        self.assertEqual(count, 5)
        self.assertIsNone(until)

    def test_parse_repeat_ends_date(self):
        start = datetime(2026, 4, 10, 9, 0, tzinfo=TZ)
        end_type, count, until = parse_repeat_ends('April 20, 2026', start)
        self.assertEqual(end_type, END_ON)
        self.assertIsNone(count)
        self.assertEqual(timezone.localtime(until).day, 20)

    def test_daily_five_occurrences(self):
        start = datetime(2026, 4, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 4, 10, 17, 0, tzinfo=TZ)
        occ = generate_repeat_occurrences(
            start, end, FREQUENCY_DAILY, interval=1, end_type=END_AFTER, count=5,
        )
        self.assertEqual(len(occ), 5)
        self.assertEqual(timezone.localtime(occ[4][0]).day, 14)

    def test_form_creates_daily_series(self):
        dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'daily',
                'repeat_interval': 1,
                'repeat_ends': '5',
            },
            client=dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visits = form.save_all()
        self.assertEqual(len(visits), 5)
        self.assertEqual(Visit.objects.filter(client=dog).count(), 5)
        series = VisitSeries.objects.get(client=dog)
        self.assertEqual(series.total_occurrences, 5)
        self.assertEqual(series.frequency, 'daily')
        self.assertEqual(visits[0].series, series)
        self.assertEqual(visits[0].series_position, 1)

    def test_single_occurrence_repeat_still_creates_series(self):
        dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'weekly',
                'repeat_interval': 2,
                'repeat_ends': '1',
            },
            client=dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visits = form.save_all()
        self.assertEqual(len(visits), 1)
        series = VisitSeries.objects.get(client=dog)
        self.assertEqual(series.frequency, 'weekly')
        self.assertEqual(series.interval, 2)
        self.assertEqual(series.total_occurrences, 1)
        self.assertEqual(series.end_type, END_AFTER)
        self.assertEqual(visits[0].series_id, series.pk)
        self.assertEqual(visits[0].series_position, 1)

    def test_non_repeat_does_not_create_series(self):
        dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'none',
            },
            client=dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visits = form.save_all()
        self.assertEqual(len(visits), 1)
        self.assertIsNone(visits[0].series_id)
        self.assertIsNone(visits[0].series_position)
        self.assertFalse(VisitSeries.objects.filter(client=dog).exists())

    def test_until_date_beyond_max_occurrences_is_rejected(self):
        dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'daily',
                'repeat_interval': 1,
                'repeat_ends': 'April 10, 2028',
            },
            client=dog,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('repeat_ends', form.errors)
        self.assertIn(str(MAX_OCCURRENCES), str(form.errors['repeat_ends']))
        self.assertFalse(Visit.objects.filter(client=dog).exists())

    def test_exactly_max_occurrences_by_count_is_allowed(self):
        dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'weekly',
                'repeat_interval': 1,
                'repeat_ends': str(MAX_OCCURRENCES),
            },
            client=dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visits = form.save_all()
        self.assertEqual(len(visits), MAX_OCCURRENCES)


class VisitFormTests(TestCase):
    def setUp(self):
        self.dog = ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))

    def test_create_visit_from_natural_language(self):
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': 'First visit',
            },
            client=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visit = form.save()
        self.assertEqual(visit.client, self.dog)
        self.assertEqual(visit.status, Visit.Status.SCHEDULED)
        self.assertEqual(visit.notes, 'First visit')

    def test_inquiry_dog_cannot_book_standard_stay(self):
        dog = ClientProfile.objects.create(
            dog_name='Bo',
            owner_name='Cassia Lewis',
            owner_email='cassia-book@example.com',
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': '',
            },
            client=dog,
        )
        self.assertFalse(form.is_valid())
        text = str(form.non_field_errors()).lower()
        self.assertIn('approved', text)
        self.assertIn('vaccination', text)
        self.assertIn('coi', text)
        self.assertFalse(Visit.objects.filter(client=dog).exists())

    def test_hidden_dog_cannot_book_new_stay(self):
        self.dog.hide()
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('hidden', str(form.non_field_errors()).lower())

    def test_approved_dog_without_vax_cannot_book(self):
        dog = ClientProfile.objects.create(
            dog_name='Bo',
            owner_name='Cassia Lewis',
            owner_email='cassia-vax@example.com',
            pipeline_stage=ClientProfile.PipelineStage.APPROVED,
        )
        CustomerOwner.ensure_for_client(dog).mark_coi_received()
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': '',
            },
            client=dog,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('vaccination', str(form.non_field_errors()).lower())

    def test_edit_skips_standard_stay_gate(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
        )
        self.dog.pipeline_stage = ClientProfile.PipelineStage.INQUIRY
        self.dog.save(update_fields=['pipeline_stage', 'updated_at'])
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 10 am',
                'end_at': 'April 11, 2026 6 pm',
                'notes': 'Moved',
            },
            instance=visit,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_overnight_visit_natural_language(self):
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 1 pm',
                'end_at': 'April 11, 2026 1 am',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visit = form.save()
        self.assertEqual(timezone.localtime(visit.scheduled_start).day, 10)
        self.assertEqual(timezone.localtime(visit.scheduled_end).day, 11)

    def test_rejects_end_before_start(self):
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 1 pm',
                'end_at': 'April 10, 2026 7 am',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())

    def test_rejects_overlapping_stay_for_same_dog(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 17, 0, tzinfo=TZ),
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 8 am',
                'end_at': 'April 11, 2026 5 pm',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('already booked', str(form.non_field_errors()).lower())
        self.assertEqual(Visit.objects.filter(client=self.dog).count(), 1)

    def test_allows_back_to_back_stays_for_same_dog(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 12, 0, tzinfo=TZ),
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 12 pm',
                'end_at': 'April 11, 2026 5 pm',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(Visit.objects.filter(client=self.dog).count(), 2)

    def test_edit_keeps_own_window(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 8, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 17, 0, tzinfo=TZ),
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 8 am',
                'end_at': 'April 11, 2026 5 pm',
                'notes': 'Same window',
            },
            instance=visit,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_edit_scheduled_visit(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 10 am',
                'end_at': 'April 11, 2026 6 pm',
                'notes': 'Moved',
            },
            instance=visit,
        )
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.notes, 'Moved')
        self.assertEqual(timezone.localtime(updated.scheduled_start).hour, 10)

    def test_edit_does_not_overwrite_non_form_fields(self):
        sent_at = datetime(2026, 4, 9, 12, 0, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
            status=Visit.Status.COMPLETED,
            calculated_fee=Decimal('25.00'),
            fee_breakdown=[{'tier': 'Daytime Visit', 'amount': '25.00'}],
            confirmation_email_sent_at=sent_at,
            notes='Original',
        )
        visit.status = Visit.Status.SCHEDULED
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 10 am',
                'end_at': 'April 11, 2026 6 pm',
                'notes': 'Moved',
            },
            instance=visit,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        visit.refresh_from_db()
        self.assertEqual(visit.notes, 'Moved')
        self.assertEqual(timezone.localtime(visit.scheduled_start).hour, 10)
        self.assertEqual(visit.status, Visit.Status.COMPLETED)
        self.assertEqual(visit.calculated_fee, Decimal('25.00'))
        self.assertEqual(visit.confirmation_email_sent_at, sent_at)

    def test_schedule_display_spans_days(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 1, 0, tzinfo=TZ),
        )
        self.assertIn('Apr 10', visit.schedule_display)
        self.assertIn('Apr 11', visit.schedule_display)

    def _fill_day(self, day_start, day_end, count):
        now = timezone.now()
        extra = []
        for i in range(count):
            dog = ClientProfile.objects.create(
                dog_name=f'Cap{i}',
                owner_name=f'Owner{i}',
                owner_email=f'cap{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=day_start,
                scheduled_end=day_end,
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)

    def test_capacity_block_is_a_form_error_before_save(self):
        start = datetime(2026, 4, 11, 13, 0, tzinfo=TZ)
        end = datetime(2026, 4, 11, 18, 0, tzinfo=TZ)
        self._fill_day(start, end, INSURANCE_CEILING)
        before = Visit.objects.count()
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())
        self.assertIn('Cannot schedule', str(form.non_field_errors()))
        self.assertEqual(Visit.objects.count(), before)
        self.assertFalse(VisitSeries.objects.filter(client=self.dog).exists())

    def test_repeat_series_blocked_before_any_visit_is_created(self):
        start = datetime(2026, 4, 11, 13, 0, tzinfo=TZ)
        end = datetime(2026, 4, 11, 18, 0, tzinfo=TZ)
        self._fill_day(start, end, INSURANCE_CEILING)
        before = Visit.objects.count()
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 1 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': '',
                'repeat_frequency': 'daily',
                'repeat_interval': 1,
                'repeat_ends': '5',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(Visit.objects.count(), before)
        self.assertFalse(VisitSeries.objects.filter(client=self.dog).exists())

    def test_edit_excludes_self_from_capacity(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        self._fill_day(
            datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            INSURANCE_CEILING - 1,
        )
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 11, 2026 2 pm',
                'end_at': 'April 11, 2026 6 pm',
                'notes': 'Moved',
            },
            instance=visit,
        )
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(timezone.localtime(updated.scheduled_start).hour, 14)

    def test_save_all_does_not_recheck_capacity(self):
        form = VisitForm(
            data={
                'business_service': default_service_pk(),
                'start_at': 'April 10, 2026 9 am',
                'end_at': 'April 10, 2026 5 pm',
                'notes': '',
                'repeat_frequency': 'daily',
                'repeat_interval': 1,
                'repeat_ends': '5',
            },
            client=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        with patch('operations.capacity.check_visit_capacity') as mock_capacity:
            visits = form.save_all()
        self.assertEqual(len(visits), 5)
        mock_capacity.assert_not_called()


class VisitIndexTests(TestCase):
    def test_hot_lookup_fields_are_indexed(self):
        indexed = {tuple(index.fields) for index in Visit._meta.indexes}
        self.assertIn(('tenant', 'scheduled_start'), indexed)
        self.assertIn(('tenant', 'scheduled_end'), indexed)
        self.assertIn(('tenant', 'status'), indexed)


class VisitCloneToDateTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )

    def _visit(self, start, end):
        return Visit.objects.create(
            client=self.dog,
            scheduled_start=start,
            scheduled_end=end,
        )

    def test_clone_preserves_local_time_of_day(self):
        source = self._visit(
            datetime(2026, 4, 11, 17, 0, tzinfo=TZ),
            datetime(2026, 4, 11, 20, 0, tzinfo=TZ),
        )
        cloned = source.clone_to_date(date(2026, 4, 20))
        local_start = timezone.localtime(cloned.scheduled_start)
        local_end = timezone.localtime(cloned.scheduled_end)
        self.assertEqual(local_start, datetime(2026, 4, 20, 17, 0, tzinfo=TZ))
        self.assertEqual(local_end, datetime(2026, 4, 20, 20, 0, tzinfo=TZ))
        self.assertEqual(cloned.cloned_from_id, source.pk)
        self.assertEqual(cloned.client_id, source.client_id)

    def test_clone_from_31st_onto_february(self):
        source = self._visit(
            datetime(2026, 1, 31, 17, 0, tzinfo=TZ),
            datetime(2026, 1, 31, 20, 0, tzinfo=TZ),
        )
        cloned = source.clone_to_date(date(2026, 2, 28))
        local_start = timezone.localtime(cloned.scheduled_start)
        self.assertEqual(local_start, datetime(2026, 2, 28, 17, 0, tzinfo=TZ))
        self.assertEqual(
            cloned.scheduled_end - cloned.scheduled_start,
            source.scheduled_end - source.scheduled_start,
        )

    def test_clone_from_31st_onto_30_day_month_keeps_overnight_duration(self):
        source = self._visit(
            datetime(2026, 1, 31, 17, 0, tzinfo=TZ),
            datetime(2026, 2, 1, 9, 0, tzinfo=TZ),
        )
        cloned = source.clone_to_date(date(2026, 4, 30))
        local_start = timezone.localtime(cloned.scheduled_start)
        local_end = timezone.localtime(cloned.scheduled_end)
        self.assertEqual(local_start, datetime(2026, 4, 30, 17, 0, tzinfo=TZ))
        self.assertEqual(local_end, datetime(2026, 5, 1, 9, 0, tzinfo=TZ))

    def test_clone_across_dst_keeps_local_clock_time(self):
        source = self._visit(
            datetime(2026, 3, 15, 17, 0, tzinfo=TZ),
            datetime(2026, 3, 15, 20, 0, tzinfo=TZ),
        )
        cloned = source.clone_to_date(date(2026, 11, 15))
        local_start = timezone.localtime(cloned.scheduled_start)
        self.assertEqual(local_start.date(), date(2026, 11, 15))
        self.assertEqual(local_start.hour, 17)
        self.assertEqual(local_start.minute, 0)