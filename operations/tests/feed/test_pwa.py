from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse

from operations.forms import BusinessProfileForm
from operations.models import (
    AccountStatement,
    BusinessProfile,
    BusinessService,
    CapacitySettings,
    ClientProfile,
    CustomerOwner,
    Visit,
)
from operations.services.geolocation import resolve_timeline_coordinates
from operations.services.statements import (
    StatementEmailError,
    format_statement_email,
    generate_weekly_statements,
    get_unbilled_summary_for_client,
    send_statement_email,
)
from operations.tests.conftest import TZ, default_service_pk


class PwaTests(TestCase):
    def test_manifest_served(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/manifest+json', response['Content-Type'])
        data = response.json()
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['short_name'], 'Dad4dogs')

    def test_service_worker_served(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])
        self.assertIn(b'skipWaiting', response.content)


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


class BusinessProfileTests(TestCase):
    def test_load_returns_singleton(self):
        first = BusinessProfile.load()
        second = BusinessProfile.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BusinessProfile.objects.count(), 1)
        self.assertIsNotNone(first.workspace_id)

    def test_save_business_details(self):
        caps = CapacitySettings.load()
        form = BusinessProfileForm(
            data={
                'business_name': 'Dad4dogs',
                'business_email': 'david@dad4dogs.ca',
                'address': '123 Main St\nToronto, ON M5V 1A1',
                'hours_of_operation': 'Mon–Fri 7:00 AM – 7:00 PM',
                'main_phone': '416-555-0100',
                'secondary_phone': '416-555-0101',
                'emergency_phone': '416-555-9999',
                'standard_capacity': 8,
                'insurance_ceiling': 10,
            },
            instance=BusinessProfile.load(),
            capacity_settings=caps,
        )
        self.assertTrue(form.is_valid(), form.errors)
        profile = form.save()
        caps.refresh_from_db()
        self.assertEqual(profile.main_phone, '416-555-0100')
        self.assertEqual(profile.emergency_phone, '416-555-9999')
        self.assertEqual(caps.standard_capacity, 8)
        self.assertEqual(caps.insurance_ceiling, 10)
        self.assertIn('Toronto', profile.formatted_address)

    def test_insurance_ceiling_cannot_be_below_standard(self):
        form = BusinessProfileForm(
            data={
                'business_name': 'Dad4dogs',
                'business_email': 'david@dad4dogs.ca',
                'address': '',
                'hours_of_operation': '',
                'main_phone': '',
                'secondary_phone': '',
                'emergency_phone': '',
                'standard_capacity': 8,
                'insurance_ceiling': 5,
            },
            instance=BusinessProfile.load(),
            capacity_settings=CapacitySettings.load(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('insurance_ceiling', form.errors)


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
        self.assertContains(response, 'Daily capacity')
        self.assertContains(response, 'Insurance max')
        self.assertContains(response, 'Google Contact Sync')
        self.assertContains(response, reverse('operations:contact_sync'))

    def test_settings_page_saves(self):
        response = self.client.post(reverse('operations:business_settings'), {
            'business_name': 'Dad4dogs',
            'business_email': 'david@dad4dogs.ca',
            'address': '123 Main St',
            'hours_of_operation': 'Daily 8 AM – 6 PM',
            'main_phone': '416-555-0100',
            'secondary_phone': '',
            'emergency_phone': '416-555-9999',
            'standard_capacity': '6',
            'insurance_ceiling': '9',
        })
        self.assertEqual(response.status_code, 302)
        profile = BusinessProfile.load()
        caps = CapacitySettings.load()
        self.assertEqual(profile.main_phone, '416-555-0100')
        self.assertEqual(profile.hours_of_operation, 'Daily 8 AM – 6 PM')
        self.assertEqual(caps.standard_capacity, 6)
        self.assertEqual(caps.insurance_ceiling, 9)

    def test_dashboard_uses_saved_standard_capacity(self):
        caps = CapacitySettings.load()
        caps.standard_capacity = 6
        caps.insurance_ceiling = 9
        caps.save(update_fields=['standard_capacity', 'insurance_ceiling', 'updated_at'])
        response = self.client.get(reverse('operations:dashboard'))
        self.assertEqual(response.context['capacity']['standard'], 6)
        self.assertEqual(response.context['capacity']['ceiling'], 9)
        self.assertContains(response, '0 / 6')


class StatementBillingTests(TestCase):
    def setUp(self):
        self.owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-billing@example.com',
            address_street='191 Grey Street',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        self.dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
        )
        self.service = BusinessService.objects.get(pk=default_service_pk())
        arrival = datetime(2026, 8, 18, 9, 0, tzinfo=TZ)
        departure = datetime(2026, 8, 18, 12, 0, tzinfo=TZ)
        self.visit = Visit.objects.create(
            client=self.dog,
            business_service=self.service,
            scheduled_start=arrival,
            scheduled_end=departure,
            status=Visit.Status.COMPLETED,
            actual_arrival=arrival,
            actual_departure=departure,
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Short Visit', 'amount': '15.00'}],
        )

    def test_generate_weekly_statements_includes_service(self):
        statements = generate_weekly_statements(week_start=date(2026, 8, 17))
        self.assertEqual(len(statements), 1)
        item = statements[0].line_items[0]
        self.assertEqual(item['visit_id'], self.visit.pk)
        self.assertEqual(item['service_name'], self.service.name)
        self.assertEqual(item['service_slug'], self.service.slug)
        body = format_statement_email(statements[0])
        self.assertIn(self.service.name, body)

    def test_unbilled_summary_before_and_after_compile(self):
        summary = get_unbilled_summary_for_client(self.dog.pk)
        self.assertEqual(summary['count'], 1)
        self.assertEqual(summary['total'], Decimal('15.00'))
        generate_weekly_statements(week_start=date(2026, 8, 17))
        summary = get_unbilled_summary_for_client(self.dog.pk)
        self.assertEqual(summary['count'], 0)
        self.assertEqual(summary['total'], Decimal('0.00'))

    @patch('operations.services.statements.send.send_gmail')
    def test_send_statement_email_marks_sent(self, mock_send):
        mock_send.return_value = {'id': 'msg-1'}
        statement = generate_weekly_statements(week_start=date(2026, 8, 17))[0]
        send_statement_email(statement)
        statement.refresh_from_db()
        self.assertEqual(statement.send_status, AccountStatement.SendStatus.SENT)
        self.assertIsNotNone(statement.sent_at)
        mock_send.assert_called_once()

    @patch('operations.services.statements.send.send_gmail')
    def test_send_statement_email_failure_leaves_status(self, mock_send):
        from operations.services.gmail_send import GmailSendError

        mock_send.side_effect = GmailSendError('token missing')
        statement = generate_weekly_statements(week_start=date(2026, 8, 17))[0]
        with self.assertRaises(StatementEmailError):
            send_statement_email(statement)
        statement.refresh_from_db()
        self.assertEqual(statement.send_status, AccountStatement.SendStatus.QUEUED)
        self.assertIsNone(statement.sent_at)

    @patch('operations.services.statements.send.send_gmail')
    def test_statement_send_view(self, mock_send):
        mock_send.return_value = {'id': 'msg-1'}
        statement = generate_weekly_statements(week_start=date(2026, 8, 17))[0]
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        url = reverse('operations:statement_send', kwargs={'pk': statement.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        statement.refresh_from_db()
        self.assertEqual(statement.send_status, AccountStatement.SendStatus.SENT)

    def test_statements_list_shows_unbilled_hint(self):
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:statements'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unbilled completed visits')

    def test_statement_detail_shows_service_and_send(self):
        statement = generate_weekly_statements(week_start=date(2026, 8, 17))[0]
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(
            reverse('operations:statement_detail', kwargs={'pk': statement.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.service.name)
        self.assertContains(response, 'Send email')
        self.assertContains(response, reverse('operations:statement_send', kwargs={'pk': statement.pk}))