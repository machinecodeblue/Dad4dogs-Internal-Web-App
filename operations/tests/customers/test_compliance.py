from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.forms import CustomerOwnerForm, VaccinationRecordForm
from operations.models import AccountStatement, ClientProfile, CustomerOwner, VaccinationRecord
from operations.models.customers import VAX_EXPIRY_WARNING_DAYS
from operations.services.addresses import (
    format_address,
    maps_search_url,
    normalize_postal_code,
    parse_legacy_address,
)
from operations.services.contacts import build_vcard
from operations.services.statements import format_statement_email


class AddressHandlingTests(TestCase):
    def test_normalize_and_format(self):
        self.assertEqual(normalize_postal_code('n6b-1g2'), 'N6B 1G2')
        self.assertEqual(
            format_address(
                street='191 Grey Street',
                unit='2B',
                city='London',
                province='ON',
                postal='N6B 1G2',
            ),
            '191 Grey Street, Unit 2B\nLondon, ON N6B 1G2',
        )

    def test_edit_form_splits_legacy_home_address(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-legacy-form@example.com',
            owner_phone='4165550100',
            home_address='191 Grey Street Unit 2\nLondon, ON N6B 1G2',
        )
        form = CustomerOwnerForm(instance=owner)
        self.assertEqual(form.initial.get('address_street'), '191 Grey Street')
        self.assertEqual(form.initial.get('address_unit'), '2')
        self.assertEqual(form.initial.get('address_city'), 'London')
        self.assertEqual(form.initial.get('address_province'), 'ON')
        self.assertEqual(form.initial.get('address_postal_code'), 'N6B 1G2')
        self.assertNotIn('\n', form.initial.get('address_street', ''))

    def test_legacy_home_address_still_displays(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-legacy@example.com',
            home_address='123 Main St\nToronto ON',
        )
        self.assertEqual(owner.formatted_address, '123 Main St\nToronto ON')
        self.assertEqual(owner.address_oneline, '123 Main St, Toronto ON')
        self.assertTrue(owner.address_maps_url.startswith('https://www.google.com/maps/search/'))

    def test_parse_legacy_extracts_postal_city_unit(self):
        parsed = parse_legacy_address(
            '191 Grey Street Unit 2, London, Ontario, N6B 1G2',
        )
        self.assertEqual(parsed['street'], '191 Grey Street')
        self.assertEqual(parsed['unit'], '2')
        self.assertEqual(parsed['city'], 'London')
        self.assertEqual(parsed['province'], 'ON')
        self.assertEqual(parsed['postal'], 'N6B 1G2')

    def test_vcard_includes_adr(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-vcard@example.com',
            owner_phone='+15195551234',
            address_street='191 Grey Street',
            address_unit='2B',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        dog = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
            owner_phone=owner.owner_phone,
        )
        vcard = build_vcard(dog)
        self.assertIn('ADR;TYPE=HOME:;Unit 2B;191 Grey Street;London;ON;N6B 1G2;Canada', vcard)

    def test_statement_email_includes_address(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-stmt@example.com',
            address_street='191 Grey Street',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        dog = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
        )
        statement = AccountStatement.objects.create(
            client=dog,
            week_start=date(2026, 8, 17),
            week_end=date(2026, 8, 23),
            line_items=[{'date': '2026-08-18', 'fee': '25.00'}],
            total_amount='25.00',
        )
        body = format_statement_email(statement)
        self.assertIn('Address: 191 Grey Street, London, ON N6B 1G2', body)

    def test_maps_url_encodes_query(self):
        url = maps_search_url('191 Grey Street, London, ON N6B 1G2')
        self.assertIn('query=191+Grey+Street', url)

    def test_customer_detail_shows_maps_link(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-maps@example.com',
            address_street='191 Grey Street',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:customer_detail', kwargs={'pk': owner.pk}))
        self.assertContains(response, 'Open in Maps')
        self.assertContains(response, '191 Grey Street')
        self.assertContains(response, 'google.com/maps/search')

    def test_dog_detail_shows_address_for_dropoff(self):
        owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-dropoff@example.com',
            address_street='191 Grey Street',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', kwargs={'pk': dog.pk}))
        self.assertContains(response, '191 Grey Street')
        self.assertContains(response, 'Open in Maps')
        self.assertContains(response, 'Drop-off address')
        self.assertNotContains(response, '<summary>Address</summary>')


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

    def test_vaccination_form_rejects_expiry_before_received(self):
        form = VaccinationRecordForm(
            data={
                'client': self.client_profile.pk,
                'papers_received': True,
                'received_at': timezone.localdate(),
                'expires_at': timezone.localdate() - timedelta(days=1),
            },
            fixed_client=self.client_profile,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('expires_at', form.errors)

    def test_vaccination_form_allows_expiry_on_received_date(self):
        today = timezone.localdate()
        form = VaccinationRecordForm(
            data={
                'client': self.client_profile.pk,
                'papers_received': True,
                'received_at': today,
                'expires_at': today,
            },
            fixed_client=self.client_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_fixed_client_ignores_posted_dog(self):
        other = ClientProfile.objects.create(
            dog_name='Max',
            owner_name='Other Owner',
            owner_email='other-vax@example.com',
        )
        today = timezone.localdate()
        form = VaccinationRecordForm(
            data={
                'client': other.pk,
                'papers_received': True,
                'received_at': today,
                'expires_at': today + timedelta(days=90),
            },
            fixed_client=self.client_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        record = form.save()
        self.assertEqual(record.client_id, self.client_profile.pk)

    def test_unchecked_papers_received_saves_false(self):
        today = timezone.localdate()
        form = VaccinationRecordForm(
            data={
                'client': self.client_profile.pk,
                'received_at': today,
                'expires_at': today + timedelta(days=90),
            },
            fixed_client=self.client_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().papers_received)

    def test_vaccination_status_expiring_within_warning_window(self):
        VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate() + timedelta(days=VAX_EXPIRY_WARNING_DAYS),
            validated=True,
        )
        self.assertTrue(self.client_profile.has_current_vaccination)
        self.assertEqual(self.client_profile.vaccination_status, 'expiring')

    def test_vaccination_status_ok_beyond_warning_window(self):
        VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate() + timedelta(days=VAX_EXPIRY_WARNING_DAYS + 1),
            validated=True,
        )
        self.assertEqual(self.client_profile.vaccination_status, 'ok')

    def test_vaccination_status_today_is_expiring_not_expired(self):
        VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate(),
            validated=True,
        )
        self.assertTrue(self.client_profile.has_current_vaccination)
        self.assertEqual(self.client_profile.vaccination_status, 'expiring')

    def test_vaccination_status_expired_and_missing(self):
        self.assertEqual(self.client_profile.vaccination_status, 'missing')
        record = VaccinationRecord.objects.create(
            client=self.client_profile,
            expires_at=timezone.localdate() - timedelta(days=1),
            validated=True,
        )
        self.assertTrue(record.is_expired)
        self.assertFalse(record.is_expiring_soon)
        dog = ClientProfile.objects.get(pk=self.client_profile.pk)
        self.assertEqual(dog.vaccination_status, 'expired')

    def test_queryset_vaccination_status_counts_and_filter(self):
        today = timezone.localdate()
        expiring = ClientProfile.objects.create(
            dog_name='Soon',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        ok = ClientProfile.objects.create(
            dog_name='Fine',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        expired = self.client_profile
        VaccinationRecord.objects.create(
            client=expiring, expires_at=today + timedelta(days=10), validated=True,
        )
        VaccinationRecord.objects.create(
            client=ok, expires_at=today + timedelta(days=90), validated=True,
        )
        VaccinationRecord.objects.create(
            client=expired, expires_at=today - timedelta(days=2), validated=True,
        )
        missing = ClientProfile.objects.create(
            dog_name='None',
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        counts = ClientProfile.objects.vaccination_status_counts()
        self.assertEqual(counts['expiring'], 1)
        self.assertEqual(counts['expired'], 1)
        self.assertEqual(counts['missing'], 1)
        self.assertEqual(counts['ok'], 1)
        self.assertEqual(
            list(
                ClientProfile.objects.filter_vaccination_status('expiring')
                .values_list('dog_name', flat=True)
            ),
            ['Soon'],
        )
        self.assertEqual(
            ClientProfile.objects.filter_vaccination_status('missing').get().pk,
            missing.pk,
        )


class VaccinationExpiryViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')
        self.owner = CustomerOwner.objects.create(
            owner_name='Cassia Lewis',
            owner_email='cassia@example.com',
        )
        today = timezone.localdate()
        self.expiring = ClientProfile.objects.create(
            dog_name='Soon',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
        )
        self.ok = ClientProfile.objects.create(
            dog_name='Fine',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
        )
        self.expired = ClientProfile.objects.create(
            dog_name='Lapsed',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
        )
        VaccinationRecord.objects.create(
            client=self.expiring,
            expires_at=today + timedelta(days=7),
            validated=True,
        )
        VaccinationRecord.objects.create(
            client=self.ok,
            expires_at=today + timedelta(days=120),
            validated=True,
        )
        VaccinationRecord.objects.create(
            client=self.expired,
            expires_at=today - timedelta(days=3),
            validated=True,
        )

    def test_client_list_vax_expiring_filter(self):
        response = self.client.get(
            reverse('operations:client_list'),
            {'vax': 'expiring'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Soon')
        self.assertNotContains(response, 'Fine')
        self.assertNotContains(response, 'Lapsed')
        self.assertContains(response, 'expire within 30 days')

    def test_client_list_vax_expired_filter(self):
        response = self.client.get(
            reverse('operations:client_list'),
            {'vax': 'expired'},
        )
        self.assertContains(response, 'Lapsed')
        self.assertContains(response, 'VAX EXPIRED')
        self.assertNotContains(response, 'Soon')

    def test_dashboard_vax_cards_link_to_filters(self):
        response = self.client.get(reverse('operations:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['vax_expiring_count'], 1)
        self.assertEqual(response.context['vax_expired_count'], 1)
        self.assertContains(response, 'Vax Expiring (30d)')
        self.assertContains(response, reverse('operations:client_list') + '?vax=expiring')
        self.assertContains(response, reverse('operations:client_list') + '?vax=expired')

    def test_add_already_expired_vaccination_warns(self):
        today = timezone.localdate()
        response = self.client.post(
            reverse('operations:add_vaccination', args=[self.expired.pk]),
            {
                'received_at': (today - timedelta(days=400)).isoformat(),
                'expires_at': (today - timedelta(days=3)).isoformat(),
                'papers_received': 'on',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already in the past')