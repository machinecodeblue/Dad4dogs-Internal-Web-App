from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from operations.models import ClientProfile, CustomerOwner
from operations.services.contacts import (
    ParsedContact,
    analyze_import,
    assess_name_quality,
    build_vcard,
    import_selected_contacts,
    is_valid_dog_name,
    parse_google_csv,
    suggest_client_fields,
)
from operations.services.phones import normalize_phone


class ContactSyncTests(TestCase):
    def setUp(self):
        self.sample_csv = (
            Path(__file__).resolve().parent.parent.parent.parent / 'Data samples' / 'google_contacts.csv'
        )

    def test_parse_google_csv(self):
        contacts, skipped = parse_google_csv(self.sample_csv.read_text(encoding='utf-8'))
        self.assertGreater(len(contacts), 0)
        self.assertGreater(len(contacts), 50)

    def test_normalize_phone_strips_formatting(self):
        self.assertEqual(normalize_phone('+1 (519) 878-4576'), '5198784576')
        self.assertEqual(normalize_phone('+15198595950'), '5198595950')

    def test_validate_phone_requires_nanp(self):
        from operations.services.phones import format_phone, tel_href, validate_phone

        self.assertEqual(validate_phone('+1 (416) 555-0100'), '4165550100')
        self.assertEqual(validate_phone(''), '')
        with self.assertRaises(ValueError):
            validate_phone('555-123')
        with self.assertRaises(ValueError):
            validate_phone('', required=True)
        self.assertEqual(format_phone('4165550100'), '(416) 555-0100')
        self.assertEqual(tel_href('416-555-0100'), 'tel:+14165550100')

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


class ContactDataTests(TestCase):
    def test_customer_emergency_and_pickup_fields(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane@example.com',
            owner_phone='416-555-0100',
            home_address='123 Main St\nToronto ON',
            emergency_contact_name='Bob Neighbor',
            emergency_contact_phone='416-555-0200',
            emergency_contact_relationship='Neighbor with house key',
            authorized_pickup_names='Bob Neighbor\nJane\'s Sister',
        )
        self.assertEqual(owner.authorized_pickup_list, ['Bob Neighbor', "Jane's Sister"])

    def test_dog_detail_shows_vet_tap_to_call(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane@example.com',
            owner_phone='416-555-0100',
        )
        dog = ClientProfile.objects.create(
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
            owner_phone=owner.owner_phone,
            dog_name='Lulu',
            vet_clinic_phone='519-555-0100',
            emergency_vet_phone='519-555-9999',
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', kwargs={'pk': dog.pk}))
        self.assertContains(response, 'tel:+15195550100')
        self.assertContains(response, 'tel:+15195559999')
        self.assertContains(response, '(519) 555-0100')