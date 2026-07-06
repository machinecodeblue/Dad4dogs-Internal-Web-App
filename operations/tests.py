from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient
from django.urls import reverse

from io import BytesIO

from PIL import Image

from operations.forms import BusinessProfileForm, CustomerOwnerForm, DogProfileForm, TimelineMomentForm, VisitForm
from operations.models import (
    BusinessProfile,
    ClientProfile,
    CustomerOwner,
    VaccinationRecord,
    Visit,
    VisitSeries,
    VisitTimelineEvent,
)
from operations.services.geolocation import resolve_timeline_coordinates
from operations.services.timeline_media import (
    TimelineMediaError,
    create_photo_asset,
    forward_timeline_event,
    log_moment_for_visits,
)
from operations.pricing import calculate_fee, is_overnight_segment
from operations.services.agenda import build_month_calendar, visits_for_day, visit_counts_between
from operations.services.visit_repeat import (
    END_AFTER,
    END_ON,
    FREQUENCY_DAILY,
    generate_repeat_occurrences,
    parse_repeat_ends,
)
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from icalendar import Calendar

from operations.services.gmail_send import (
    BOOKING_ICS_FILENAME,
    GmailSendError,
    build_booking_invite_message,
    send_gmail,
)
from operations.services.visit_email import (
    VisitEmailError,
    format_booking_confirmation,
    generate_booking_ics,
    send_booking_confirmation,
)
from operations.services.contacts import (
    ParsedContact,
    analyze_import,
    assess_name_quality,
    build_vcard,
    import_selected_contacts,
    is_valid_dog_name,
    normalize_phone,
    parse_google_csv,
    suggest_client_fields,
)

TZ = ZoneInfo('America/Toronto')


class CustomerOwnerFormTests(TestCase):
    def test_create_customer(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane@example.com',
            'owner_phone': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        owner = form.save()
        self.assertEqual(owner.owner_name, 'Jane Doe')
        self.assertEqual(ClientProfile.objects.filter(owner_email='jane@example.com').count(), 0)


class DogProfileFormTests(TestCase):
    def setUp(self):
        self.owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )

    def test_create_dog_for_customer(self):
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        dog = form.save()
        self.assertEqual(dog.dog_name, 'Kobe')
        self.assertEqual(dog.owner_email, 'jane@example.com')

    def test_rejects_owner_first_name_as_dog_name(self):
        form = DogProfileForm(
            data={
                'dog_name': 'Jane',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertFalse(form.is_valid())

    def test_rejects_duplicate_dog(self):
        ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertFalse(form.is_valid())


class ContactSyncTests(TestCase):
    def setUp(self):
        self.sample_csv = (
            Path(__file__).resolve().parent.parent / 'Data samples' / 'google_contacts.csv'
        )

    def test_parse_google_csv(self):
        contacts, skipped = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        self.assertGreater(len(contacts), 0)
        self.assertGreater(len(contacts), 50)

    def test_normalize_phone_strips_formatting(self):
        self.assertEqual(normalize_phone('+1 (519) 878-4576'), '5198784576')
        self.assertEqual(normalize_phone('+15198595950'), '5198595950')

    def test_detects_duplicate_phones_in_csv(self):
        contacts, _ = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        analysis = analyze_import(contacts)
        phone_values = [g.match_value for g in analysis.csv_phone_duplicates]
        self.assertIn('5198784576', phone_values)

    def test_detects_db_email_match(self):
        ClientProfile.objects.create(
            dog_name='Bo',
            owner_name='Cassia Lewis',
            owner_email='cassia.belanger@gmail.com',
        )
        contacts, _ = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        analysis = analyze_import(contacts)
        self.assertTrue(any(
            g.match_value == 'cassia.belanger@gmail.com'
            for g in analysis.db_email_matches
        ))

    def test_detects_customer_only_db_match(self):
        CustomerOwner.objects.create(
            owner_name='Kathleen Kelly',
            owner_email='kathleeneak@gmail.com',
        )
        contacts, _ = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        analysis = analyze_import(contacts)
        match = next(
            (g for g in analysis.db_email_matches if g.match_value == 'kathleeneak@gmail.com'),
            None,
        )
        self.assertIsNotNone(match)
        self.assertEqual(len(match.existing_clients), 0)
        self.assertEqual(len(match.existing_owners), 1)
        self.assertEqual(match.existing_owners[0].owner_name, 'Kathleen Kelly')

    def test_flags_dog_nickname_as_name_issue(self):
        contact = ParsedContact(
            row_number=10,
            first_name='bailey contact',
            last_name='',
            emails=['test@example.com'],
            phones=['+15195551234'],
        )
        issues = assess_name_quality(contact)
        self.assertTrue(any('dog nickname' in i.lower() for i in issues))

    def test_person_name_suggests_no_dog(self):
        contact = ParsedContact(
            row_number=55,
            first_name='Kathleen',
            last_name='Kelly',
            emails=['kathleeneak@gmail.com'],
        )
        suggested = suggest_client_fields(contact)
        self.assertEqual(suggested['dog_name'], '')
        self.assertEqual(suggested['owner_name'], 'Kathleen Kelly')
        self.assertFalse(suggested['has_dog'])

    def test_notes_dog_name_suggestion(self):
        contact = ParsedContact(
            row_number=18,
            first_name='Cassia',
            last_name='LEWIS',
            emails=['cassia.belanger@gmail.com'],
            notes="Dog's name is Bo",
        )
        suggested = suggest_client_fields(contact)
        self.assertEqual(suggested['dog_name'], 'Bo')
        self.assertIn('Cassia', suggested['owner_name'])
        self.assertTrue(suggested['has_dog'])

    def test_selective_import_creates_customer_and_dog(self):
        selectable = [{
            'row_number': 5,
            'can_import': True,
            'suggested_dog_name': 'Kobe',
            'suggested_owner_name': 'Jane Doe',
            'suggested_email': 'jane@example.com',
            'suggested_phone': '+15195551234',
            'notes': '',
            'name_issues': [],
        }]
        created_owners, created_dogs, errors = import_selected_contacts(selectable, [5], {})
        self.assertEqual(len(created_owners), 1)
        self.assertEqual(len(created_dogs), 1)
        self.assertEqual(len(errors), 0)
        self.assertEqual(created_dogs[0].dog_name, 'Kobe')

    def test_selective_import_customer_only(self):
        selectable = [{
            'row_number': 55,
            'can_import': True,
            'suggested_dog_name': '',
            'suggested_owner_name': 'Kathleen Kelly',
            'suggested_email': 'kathleen@example.com',
            'suggested_phone': '',
            'notes': '',
            'name_issues': ['looks like owner'],
        }]
        created_owners, created_dogs, errors = import_selected_contacts(selectable, [55], {})
        self.assertEqual(len(created_owners), 1)
        self.assertEqual(len(created_dogs), 0)
        self.assertEqual(len(errors), 0)
        self.assertEqual(created_owners[0].owner_name, 'Kathleen Kelly')
        self.assertFalse(ClientProfile.objects.filter(owner_email='kathleen@example.com').exists())

    def test_import_skips_invalid_dog_name_override(self):
        selectable = [{
            'row_number': 7,
            'can_import': True,
            'suggested_dog_name': '',
            'suggested_owner_name': 'Kathleen Kelly',
            'suggested_email': 'kathleen2@example.com',
            'suggested_phone': '',
            'notes': '',
            'name_issues': [],
        }]
        created_owners, created_dogs, errors = import_selected_contacts(
            selectable, [7], {7: {'dog_name': 'Kathleen'}},
        )
        self.assertEqual(len(created_owners), 1)
        self.assertEqual(len(created_dogs), 0)
        self.assertFalse(ClientProfile.objects.filter(dog_name='Kathleen').exists())

    def test_name_review_count_in_analysis(self):
        contacts, _ = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        analysis = analyze_import(contacts)
        self.assertGreater(analysis.name_issues_count, 10)
        self.assertGreater(len(analysis.name_review_contacts), 10)

    def test_vcard_contains_client_fields(self):
        client = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
            owner_phone='+15195551234',
        )
        vcard = build_vcard(client)
        self.assertIn('BEGIN:VCARD', vcard)
        self.assertIn('jane@example.com', vcard)
        self.assertIn('Kobe', vcard)


class NeedsDogNameTests(TestCase):
    def test_kathleen_kelly_pattern(self):
        dog = ClientProfile.objects.create(
            dog_name='Kathleen',
            owner_name='Kathleen Kelly',
            owner_email='kathleeneak@gmail.com',
        )
        self.assertTrue(dog.needs_dog_name)
        self.assertFalse(is_valid_dog_name('Kathleen', 'Kathleen Kelly'))


class CustomerEditTests(TestCase):
    def test_edit_customer(self):
        owner = CustomerOwner.objects.create(
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        form = CustomerOwnerForm(
            data={
                'owner_name': 'Cassia Lewis',
                'owner_email': 'cassia@example.com',
                'owner_phone': '+15195551234',
            },
            instance=owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.owner_phone, '+15195551234')

    def test_add_second_dog_same_owner(self):
        owner = CustomerOwner.objects.create(
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        DogProfileForm(
            data={
                'dog_name': 'Bo',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=owner,
        ).save()
        form = DogProfileForm(
            data={
                'dog_name': 'Max',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(
            ClientProfile.objects.filter(owner_email='cassia@example.com').count(),
            2,
        )


class ComplianceTests(TestCase):
    def setUp(self):
        self.client_profile = ClientProfile.objects.create(
            dog_name='Bo',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )

    def test_coi_at_owner_level_shared_across_dogs(self):
        owner = CustomerOwner.ensure_for_client(self.client_profile)
        other_dog = ClientProfile.objects.create(
            dog_name='Max',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        owner.mark_coi_received()
        self.assertEqual(other_dog.customer_owner.coi_status, 'received')

    def test_vaccination_linked_to_dog_with_expiry(self):
        expires = timezone.localdate() + timedelta(days=180)
        record = VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=expires,
            vaccination_details='Rabies, kennel cough',
            vet_clinic='Datta Veterinarian Hospital',
        )
        self.assertFalse(self.client_profile.has_current_vaccination)
        record.mark_validated()
        self.assertTrue(self.client_profile.has_current_vaccination)

    def test_expired_vaccination_not_current(self):
        record = VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate() - timedelta(days=1),
            validated=True,
        )
        self.assertTrue(record.is_expired)
        self.assertFalse(self.client_profile.has_current_vaccination)

    def test_separate_dogs_separate_vaccination_records(self):
        other_dog = ClientProfile.objects.create(
            dog_name='Max',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate() + timedelta(days=90),
            validated=True,
        )
        VaccinationRecord.objects.create(
            client=other_dog,
            expires_at=timezone.localdate() + timedelta(days=90),
        )
        self.assertTrue(self.client_profile.has_current_vaccination)
        self.assertFalse(other_dog.has_current_vaccination)


class AgendaTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        )

    def test_visits_for_day_includes_overnight_span(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 1, 0, tzinfo=TZ),
        )
        day10 = visits_for_day(date(2026, 4, 10))
        day11 = visits_for_day(date(2026, 4, 11))
        self.assertEqual(day10.count(), 1)
        self.assertEqual(day11.count(), 1)

    def test_visit_counts_by_day(self):
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
        )
        counts = visit_counts_between(date(2026, 4, 1), date(2026, 4, 30))
        self.assertEqual(counts[date(2026, 4, 10)], 1)
        self.assertEqual(counts[date(2026, 4, 11)], 0)

    def test_build_month_calendar_marks_selected_day(self):
        weeks = build_month_calendar(2026, 4, date(2026, 4, 10), date(2026, 4, 5))
        flat = [cell for week in weeks for cell in week if cell]
        selected = [cell for cell in flat if cell['is_selected']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['day'], 10)


class DatetimeParseTests(TestCase):
    def test_parses_natural_start(self):
        dt = parse_datetime_text('April 11th 2026 5 p.m.')
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 11)
        self.assertEqual(dt.hour, 17)

    def test_parses_natural_end(self):
        start = parse_datetime_text('April 11, 2026 1 pm')
        end = parse_datetime_text('April 28, 5:00 p.m', default=start)
        self.assertEqual(end.month, 4)
        self.assertEqual(end.day, 28)
        self.assertEqual(end.hour, 17)

    def test_format_display(self):
        dt = parse_datetime_text('April 11, 2026 5 pm')
        self.assertIn('Apr 11, 2026', format_datetime_display(dt))
        self.assertIn('5:00 PM', format_datetime_display(dt))


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
        dog = ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        )
        form = VisitForm(
            data={
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


class VisitFormTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        )

    def test_create_visit_from_natural_language(self):
        form = VisitForm(
            data={
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

    def test_overnight_visit_natural_language(self):
        form = VisitForm(
            data={
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
                'start_at': 'April 10, 2026 1 pm',
                'end_at': 'April 10, 2026 7 am',
                'notes': '',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())

    def test_edit_scheduled_visit(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 10, 17, 0, tzinfo=TZ),
        )
        form = VisitForm(
            data={
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

    def test_schedule_display_spans_days(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 10, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 1, 0, tzinfo=TZ),
        )
        self.assertIn('Apr 10', visit.schedule_display)
        self.assertIn('Apr 11', visit.schedule_display)


class PricingEngineTests(TestCase):
    def test_short_visit(self):
        start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('15.00'))
        self.assertEqual(items[0]['tier'], 'Short Visit')

    def test_daytime_visit(self):
        start = datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 18, 0, tzinfo=TZ)
        fee, _ = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('25.00'))

    def test_overnight_priority_over_daytime_hours(self):
        """1 PM to 1 AM (12h) must be Overnight, not Daytime."""
        start = datetime(2026, 3, 10, 13, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 1, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('37.50'))
        self.assertEqual(items[0]['tier'], 'Overnight')
        self.assertTrue(is_overnight_segment(start, end))

    def test_multiday_24h_plus_3h(self):
        start = datetime(2026, 3, 10, 13, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 16, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('52.50'))
        tiers = [i['tier'] for i in items]
        self.assertIn('Overnight (24h block)', tiers)
        self.assertIn('Short Visit', tiers)

    def test_multiday_24h_plus_11h(self):
        start = datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 19, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('62.50'))
        tiers = [i['tier'] for i in items]
        self.assertIn('Overnight (24h block)', tiers)
        self.assertIn('Daytime Visit', tiers)

    def test_line_items_are_json_serializable(self):
        start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        _, items = calculate_fee(start, end)
        self.assertEqual(items[0]['amount'], '15.00')
        self.assertIsInstance(items[0]['amount'], str)


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


@override_settings(GMAIL_OAUTH_DIR=Path('/nonexistent/oauth-dir'))
class GmailSendTests(TestCase):
    def test_send_gmail_requires_token(self):
        with self.assertRaises(GmailSendError) as ctx:
            send_gmail('Subject', 'Body', 'test@example.com')
        self.assertIn('oauth_setup.py', str(ctx.exception))


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

    @patch('operations.models.scheduling.timezone.now')
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


class BusinessProfileTests(TestCase):
    def test_load_returns_singleton(self):
        first = BusinessProfile.load()
        second = BusinessProfile.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BusinessProfile.objects.count(), 1)

    def test_save_business_details(self):
        form = BusinessProfileForm(data={
            'business_name': 'Dad4dogs',
            'business_email': 'david@dad4dogs.ca',
            'address': '123 Main St\nToronto, ON M5V 1A1',
            'hours_of_operation': 'Mon–Fri 7:00 AM – 7:00 PM',
            'main_phone': '416-555-0100',
            'secondary_phone': '416-555-0101',
            'emergency_phone': '416-555-9999',
        }, instance=BusinessProfile.load())
        self.assertTrue(form.is_valid(), form.errors)
        profile = form.save()
        self.assertEqual(profile.main_phone, '416-555-0100')
        self.assertEqual(profile.emergency_phone, '416-555-9999')
        self.assertIn('Toronto', profile.formatted_address)


class BusinessSettingsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')

    def test_settings_page_loads(self):
        response = self.client.get(reverse('operations:business_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Business Settings')
        self.assertContains(response, 'Emergency Contact Number')

    def test_settings_page_saves(self):
        response = self.client.post(reverse('operations:business_settings'), {
            'business_name': 'Dad4dogs',
            'business_email': 'david@dad4dogs.ca',
            'address': '123 Main St',
            'hours_of_operation': 'Daily 8 AM – 6 PM',
            'main_phone': '416-555-0100',
            'secondary_phone': '',
            'emergency_phone': '416-555-9999',
        })
        self.assertEqual(response.status_code, 302)
        profile = BusinessProfile.load()
        self.assertEqual(profile.main_phone, '416-555-0100')
        self.assertEqual(profile.hours_of_operation, 'Daily 8 AM – 6 PM')


def _test_image_file(name='moment.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (1200, 900), color=(34, 139, 34)).save(buffer, format='JPEG')
    buffer.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, buffer.read(), content_type='image/jpeg')


class GeolocationTests(TestCase):
    def test_resolve_device_coordinates(self):
        lat, lng, used_fallback, label = resolve_timeline_coordinates('43.01', '-81.23')
        self.assertFalse(used_fallback)
        self.assertEqual(label, '')
        self.assertEqual(lat, Decimal('43.01'))

    def test_resolve_fallback_coordinates(self):
        BusinessProfile.load().save()
        lat, lng, used_fallback, label = resolve_timeline_coordinates('', '')
        self.assertTrue(used_fallback)
        self.assertIn('191 Grey Street', label)
        self.assertEqual(lat, Decimal('43.002700'))


class TimelineMomentFormTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
        )

    def test_requires_single_media_type(self):
        form = TimelineMomentForm(
            data={'caption_notes': 'Playing fetch', 'visit_ids': [str(self.visit.pk)]},
            files={
                'photo_gallery': _test_image_file(),
                'video': _test_image_file('clip.mp4'),
            },
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())

    def test_accepts_gallery_photo_only(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': 'Nap time',
                'latitude': '43.0',
                'longitude': '-81.2',
                'visit_ids': [str(self.visit.pk)],
            },
            files={'photo_gallery': _test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['media_kind'], 'photo')


class VisitTimelineTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='david', password='testpass123')
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.dog_two = ClientProfile.objects.create(
            dog_name='Bailey',
            owner_name='John Doe',
            owner_email='john@example.com',
        )
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 7, 6, 9, 5, tzinfo=TZ),
        )
        self.visit_two = Visit.objects.create(
            client=self.dog_two,
            scheduled_start=datetime(2026, 7, 6, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 7, 6, 17, 0, tzinfo=TZ),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=datetime(2026, 7, 6, 9, 10, tzinfo=TZ),
        )

    def test_timeline_blocked_when_not_checked_in(self):
        self.visit.status = Visit.Status.SCHEDULED
        self.visit.save()
        response = self.client.get(reverse('operations:visit_timeline', args=[self.visit.pk]))
        self.assertEqual(response.status_code, 302)

    def test_timeline_page_renders_for_checked_in_visit(self):
        response = self.client.get(reverse('operations:visit_timeline', args=[self.visit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log Moment')
        self.assertContains(response, 'capture="environment"', html=False)
        self.assertContains(response, 'Choose Photo (gallery)')

    def test_create_photo_asset_pipeline(self):
        asset = create_photo_asset(
            uploaded_file=_test_image_file(),
            caption_notes='Zoomies in the yard',
            latitude=Decimal('43.010000'),
            longitude=Decimal('-81.230000'),
            used_fallback=False,
            fallback_label='',
            original_visit=self.visit,
        )
        self.assertEqual(asset.media_type, 'photo')
        self.assertTrue(asset.photo_high_res.name.endswith('.jpg'))
        self.assertTrue(asset.photo_thumbnail.name.endswith('.webp'))

    def test_post_photo_moment_for_multiple_dogs(self):
        response = self.client.post(
            reverse('operations:visit_timeline', args=[self.visit.pk]),
            {
                'caption_notes': 'Pack photo',
                'latitude': '43.01',
                'longitude': '-81.23',
                'visit_ids': [str(self.visit.pk), str(self.visit_two.pk)],
                'photo_gallery': _test_image_file(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.visit.timeline_events.count(), 1)
        self.assertEqual(self.visit_two.timeline_events.count(), 1)
        asset = self.visit.timeline_events.first().media_asset
        self.assertEqual(self.visit_two.timeline_events.first().media_asset_id, asset.pk)

    def test_forward_view_post(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=_test_image_file(),
            caption_notes='Share me',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        response = self.client.post(
            reverse(
                'operations:visit_timeline_forward',
                args=[self.visit.pk, events[0].pk],
            ),
            {'visit_ids': [str(self.visit_two.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.visit_two.timeline_events.count(), 1)

    def test_forward_preserves_capture_time(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=_test_image_file(),
            caption_notes='Yard time',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        source = events[0]
        captured = source.captured_at
        forwarded = forward_timeline_event(
            source_event=source,
            target_visit_ids=[self.visit_two.pk],
        )
        self.assertEqual(forwarded[0].captured_at, captured)
        self.assertTrue(forwarded[0].is_forward)

    def test_forward_blocked_after_checkout(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=_test_image_file(),
            caption_notes='',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.visit_two.status = Visit.Status.COMPLETED
        self.visit_two.save()
        with self.assertRaises(TimelineMediaError):
            forward_timeline_event(
                source_event=events[0],
                target_visit_ids=[self.visit_two.pk],
            )

    def test_reject_oversized_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from operations.services.timeline_media import create_video_asset

        huge = SimpleUploadedFile('big.mp4', b'x' * (26 * 1024 * 1024), content_type='video/mp4')
        with self.assertRaises(TimelineMediaError):
            create_video_asset(
                uploaded_file=huge,
                caption_notes='',
                latitude=Decimal('43.0'),
                longitude=Decimal('-81.2'),
                used_fallback=False,
                fallback_label='',
                original_visit=self.visit,
            )