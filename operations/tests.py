from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient
from django.urls import reverse

from io import BytesIO

from PIL import Image

from operations.forms import (
    BusinessProfileForm,
    CustomerOwnerForm,
    DogProfileForm,
    IntakeWizardForm,
    TimelineMomentForm,
    VaccinationRecordForm,
    VisitForm,
)
from operations.models import (
    BusinessProfile,
    CapacitySettings,
    ClientProfile,
    CustomerOwner,
    MediaComment,
    MediaReaction,
    PendingCalendarEvent,
    SharedMediaLink,
    TimelineMediaAsset,
    VaccinationRecord,
    Visit,
    VisitSeries,
    VisitTimelineEvent,
)
from operations.models.customers import VAX_EXPIRY_WARNING_DAYS

def _default_service_pk(slug='overnight_stay'):
    from operations.models import BusinessService
    from operations.services.context_tenant import get_active_workspace
    workspace = get_active_workspace()
    service = BusinessService.objects.filter(tenant=workspace, slug=slug).first()
    if service is None:
        service = BusinessService.objects.filter(tenant=workspace, is_active=True).first()
    return service.pk

from operations.models.scheduling import timeline_asset_upload_path
from operations.services.feed_interactions import set_reaction, add_comment, get_or_create_share_link
from operations.services.geolocation import resolve_timeline_coordinates
from operations.services.timeline_media import (
    TimelineMediaError,
    create_photo_asset,
    forward_timeline_event,
    log_moment_for_visits,
)
from operations.capacity import (
    INSURANCE_CEILING,
    _capacity_span_dates,
    check_visit_capacity,
    count_dogs_on_day,
)
from operations.pricing import calculate_fee, is_overnight_segment
from operations.services.agenda import build_month_calendar, visits_for_day, visit_counts_between
from operations.services.visit_repeat import (
    END_AFTER,
    END_ON,
    FREQUENCY_DAILY,
    MAX_OCCURRENCES,
    generate_repeat_occurrences,
    parse_repeat_ends,
)
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from icalendar import Calendar

from operations.services.gmail_send import (
    BOOKING_ICS_FILENAME,
    GmailSendError,
    _load_credentials,
    build_booking_invite_message,
    send_gmail,
)
from operations.services.feed_access import VISITOR_COOKIE_NAME
from operations.services.feed_slugs import dog_slug_from_name, generate_feed_secret
from operations.services.visit_email import (
    VisitEmailError,
    format_booking_confirmation,
    generate_booking_ics,
    send_booking_confirmation,
)
from operations.services.addresses import (
    format_address,
    maps_search_url,
    normalize_postal_code,
    parse_legacy_address,
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
from operations.services.statements import format_statement_email

TZ = ZoneInfo('America/Toronto')


def _ready_for_standard_stay(dog: ClientProfile) -> ClientProfile:
    dog.pipeline_stage = ClientProfile.PipelineStage.APPROVED
    dog.save(update_fields=['pipeline_stage', 'updated_at'])
    CustomerOwner.ensure_for_client(dog).mark_coi_received()
    VaccinationRecord.objects.create(
        client=dog,
        expires_at=timezone.localdate() + timedelta(days=180),
        validated=True,
    )
    return dog


class CustomerOwnerFormTests(TestCase):
    def test_create_customer(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane@example.com',
            'owner_phone': '416-555-0100',
        })
        self.assertTrue(form.is_valid(), form.errors)
        owner = form.save()
        self.assertEqual(owner.owner_name, 'Jane Doe')
        self.assertEqual(owner.owner_email, 'jane@example.com')
        self.assertEqual(ClientProfile.objects.filter(owner_email='jane@example.com').count(), 0)

    def test_lowercases_and_rejects_duplicate_email(self):
        CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane@example.com',
            owner_phone='4165550100',
        )
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Two',
            'owner_email': 'Jane@Example.com',
            'owner_phone': '416-555-0100',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('owner_email', form.errors)

        fresh = CustomerOwnerForm(data={
            'owner_name': 'Alex Green',
            'owner_email': 'Alex@Example.com',
            'owner_phone': '416-555-0100',
        })
        self.assertTrue(fresh.is_valid(), fresh.errors)
        self.assertEqual(fresh.save().owner_email, 'alex@example.com')

    def test_partial_address_is_rejected(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-partial@example.com',
            'owner_phone': '416-555-0100',
            'address_postal_code': 'N6B 1G2',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('address_street', form.errors)
        self.assertIn('address_city', form.errors)
        self.assertIn('address_province', form.errors)

    def test_empty_province_is_valid_when_address_is_blank(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-noprov@example.com',
            'owner_phone': '416-555-0100',
            'address_province': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['address_province'], '')

    def test_province_alias_coerces_to_code(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-ont@example.com',
            'owner_phone': '416-555-0100',
            'address_street': '191 Grey Street',
            'address_city': 'London',
            'address_province': 'Ontario',
            'address_postal_code': 'N6B 1G2',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['address_province'], 'ON')

    def test_primary_phone_required(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane@example.com',
            'owner_phone': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('owner_phone', form.errors)

    def test_normalizes_owner_and_emergency_phones(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-phone@example.com',
            'owner_phone': '+1 (416) 555-0100',
            'emergency_contact_phone': '416-555-0200',
        })
        self.assertTrue(form.is_valid(), form.errors)
        owner = form.save()
        self.assertEqual(owner.owner_phone, '4165550100')
        self.assertEqual(owner.emergency_contact_phone, '4165550200')

    def test_rejects_invalid_owner_phone(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-badphone@example.com',
            'owner_phone': '555-123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('owner_phone', form.errors)

    def test_cleans_authorized_pickup_names(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-pickup@example.com',
            'owner_phone': '416-555-0100',
            'authorized_pickup_names': '  Bob Neighbor  \n\n\nJane\'s Sister \n  \n',
        })
        self.assertTrue(form.is_valid(), form.errors)
        owner = form.save()
        self.assertEqual(owner.authorized_pickup_names, "Bob Neighbor\nJane's Sister")
        self.assertEqual(owner.authorized_pickup_list, ['Bob Neighbor', "Jane's Sister"])

    def test_rejects_invalid_emergency_phone(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-bademerg@example.com',
            'owner_phone': '416-555-0100',
            'emergency_contact_phone': 'call me',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('emergency_contact_phone', form.errors)

    def test_saves_structured_address_and_rebuilds_home_address(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-addr@example.com',
            'owner_phone': '416-555-0100',
            'address_street': '191 Grey Street',
            'address_unit': '2B',
            'address_city': 'London',
            'address_province': 'ON',
            'address_postal_code': 'n6b1g2',
        })
        self.assertTrue(form.is_valid(), form.errors)
        owner = form.save()
        self.assertEqual(owner.address_postal_code, 'N6B 1G2')
        self.assertEqual(
            owner.home_address,
            '191 Grey Street, Unit 2B\nLondon, ON N6B 1G2',
        )
        self.assertEqual(
            owner.address_oneline,
            '191 Grey Street, Unit 2B, London, ON N6B 1G2',
        )
        self.assertIn('191+Grey+Street', owner.address_maps_url)

    def test_rejects_invalid_postal_code(self):
        form = CustomerOwnerForm(data={
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-badpostal@example.com',
            'owner_phone': '416-555-0100',
            'address_postal_code': '12345',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('address_postal_code', form.errors)


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
        from operations.models import AccountStatement

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


class CognitiveLoadUXTests(TestCase):
    """Client/list/detail screens follow one-handed cognitive-load rules."""

    def setUp(self):
        self.owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-ux@example.com',
            owner_phone='4165550100',
            address_street='191 Grey Street',
            address_city='London',
            address_province='ON',
            address_postal_code='N6B 1G2',
        )
        self.dog = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
            owner_phone=self.owner.owner_phone,
            pipeline_stage=ClientProfile.PipelineStage.APPROVED,
        )
        user = get_user_model().objects.create_user('david-ux', 'ux@example.com', 'pass')
        self.client.force_login(user)

    def test_client_list_is_owner_first_with_view_and_book(self):
        response = self.client.get(reverse('operations:client_list'))
        self.assertContains(response, 'Doe, Jane')
        self.assertContains(response, reverse('operations:customer_detail', args=[self.owner.pk]))
        self.assertContains(response, 'id="client-search"')
        self.assertContains(response, '+ New Client')
        self.assertNotContains(response, 'Customer only')
        self.assertNotContains(response, 'Google Contact Sync')
        self.assertNotContains(response, '>View<')
        self.assertContains(response, 'class="title">Kobe<')
        self.assertContains(response, reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'NO VAX')
        self.assertContains(response, 'Needs vax')
        self.assertContains(response, reverse('operations:dog_vaccinations', args=[self.dog.pk]))
        self.assertNotContains(response, 'class="book-link">Book<')
        self.assertContains(response, '(416) 555-0100')
        self.assertNotContains(response, 'class="badge badge-ok"')

    def test_client_list_shows_book_when_stay_is_ready(self):
        self.owner.mark_coi_received()
        VaccinationRecord.objects.create(
            client=self.dog,
            received_at=timezone.localdate(),
            expires_at=timezone.localdate() + timedelta(days=120),
            validated=True,
            papers_received=True,
        )
        response = self.client.get(reverse('operations:client_list'))
        self.assertContains(response, 'class="book-link">Book<')
        self.assertContains(response, reverse('operations:visit_create', args=[self.dog.pk]))
        self.assertNotContains(response, 'Needs vax')
        self.assertNotContains(response, 'NO VAX')

    def test_owner_list_name_is_last_comma_first(self):
        self.assertEqual(self.owner.list_name, 'Doe, Jane')
        self.assertEqual(self.owner.list_sort_key, ('doe', 'jane'))

    def test_dog_detail_keeps_call_and_emergency_as_primary_actions(self):
        self.dog.emergency_vet_phone = '5195559999'
        self.dog.save(update_fields=['emergency_vet_phone', 'updated_at'])
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'card-kicker">Dog')
        self.assertContains(response, '(416) 555-0100')
        self.assertContains(response, '>Call<')
        self.assertContains(response, '<h2>Veterinary</h2>')
        self.assertContains(response, 'Emergency vet')
        self.assertContains(response, 'btn-warn')
        self.assertContains(response, reverse('operations:dog_vaccinations', args=[self.dog.pk]))
        self.assertContains(response, 'Vaccinations')
        self.assertNotContains(response, 'Schedule stay')
        self.assertContains(response, reverse('operations:dog_edit', args=[self.dog.pk]))
        self.assertContains(response, '<summary>More actions</summary>')
        self.assertContains(response, 'Hide dog')
        self.assertNotContains(response, 'Vaccination records')

    def test_vaccination_page_omits_green_ok_badges(self):
        VaccinationRecord.objects.create(
            client=self.dog,
            received_at=timezone.localdate(),
            expires_at=timezone.localdate() + timedelta(days=120),
            validated=True,
            papers_received=True,
        )
        response = self.client.get(reverse('operations:dog_vaccinations', args=[self.dog.pk]))
        self.assertNotContains(response, 'CURRENT VALIDATED VAX')
        self.assertNotContains(response, 'class="badge badge-ok"')

    def test_dashboard_omits_always_on_stats_and_ok_badges(self):
        response = self.client.get(reverse('operations:dashboard'))
        self.assertNotContains(response, 'Approved Dogs')
        self.assertNotContains(response, 'Standard Max')
        self.assertNotContains(response, 'class="badge badge-ok"')
        self.assertContains(response, '<summary>Calendar feed</summary>')
        self.assertEqual(response.context['capacity']['count'], 0)
        self.assertEqual(response.context['capacity']['standard'], 8)
        self.assertContains(response, '0 / 8')
        self.assertContains(response, 'of 8 standard capacity')

    def test_customer_detail_is_a_profile_not_an_action_drawer(self):
        response = self.client.get(reverse('operations:customer_detail', args=[self.owner.pk]))
        self.assertContains(response, reverse('operations:customer_edit', args=[self.owner.pk]))
        self.assertContains(response, '>Edit<')
        self.assertContains(response, 'Primary owner contact')
        self.assertContains(response, 'jane-ux@example.com')
        self.assertContains(response, 'COI not sent')
        self.assertContains(response, '(416) 555-0100')
        self.assertNotContains(response, '<h2>Certificate of insurance</h2>')
        self.assertNotContains(response, '<summary>Address</summary>')
        self.assertNotContains(response, '<h2>Emergency')
        self.assertNotContains(response, '<summary>More actions</summary>')
        self.assertNotContains(response, 'Back to Clients')

    def test_customer_detail_emergency_contacts_are_in_one_disclosure(self):
        self.owner.emergency_contact_name = 'Bob Neighbor'
        self.owner.emergency_contact_phone = '4165550200'
        self.owner.emergency_contact_relationship = 'Neighbor with house key'
        self.owner.authorized_pickup_names = 'Bob Neighbor\nJane Sister'
        self.owner.save()
        response = self.client.get(reverse('operations:customer_detail', args=[self.owner.pk]))
        self.assertContains(response, '<h2>Emergency &amp; Pickups</h2>')
        self.assertContains(response, 'Emergency contact')
        self.assertContains(response, 'Authorized pickup')
        self.assertContains(response, 'Bob Neighbor')
        self.assertContains(response, 'Neighbor with house key')
        self.assertContains(response, 'tel:+14165550200')
        self.assertContains(response, 'btn-warn')
        self.assertContains(response, '(416) 555-0200')
        self.assertContains(response, 'Jane Sister')
        html = response.content.decode()
        emergency_card = html.find('<h2>Emergency &amp; Pickups</h2>')
        self.assertGreater(emergency_card, html.find('Primary owner contact'))
        after = html[emergency_card:]
        self.assertIn('btn-warn', after)
        self.assertIn('(416) 555-0200', after)

    def test_customer_detail_received_coi_is_a_mark_beside_the_name(self):
        self.owner.mark_coi_received()
        response = self.client.get(reverse('operations:customer_detail', args=[self.owner.pk]))
        self.assertContains(response, 'title="COI on file"')
        self.assertContains(response, '✓')
        self.assertNotContains(response, 'COI not sent')
        self.assertNotContains(response, '<h2>Certificate of insurance</h2>')

    def test_staff_pages_use_top_nav_not_bottom_bar(self):
        response = self.client.get(reverse('operations:dashboard'))
        html = response.content.decode()
        self.assertNotIn('bottom-nav', html)
        self.assertIn('app-header', html)
        self.assertIn('app-primary-nav', html)
        self.assertIn('nav-drawer', html)
        self.assertContains(response, reverse('operations:mobile_checkin'))
        self.assertContains(response, reverse('operations:client_list'))
        self.assertContains(response, reverse('operations:statements'))
        self.assertContains(response, reverse('operations:business_settings'))
        self.assertContains(response, reverse('operations:pending_events'))
        self.assertContains(response, reverse('operations:contact_sync'))
        # Billing / Settings live in the drawer, not as primary peers of Check-In
        primary = html.split('app-primary-nav', 1)[1].split('</nav>', 1)[0]
        self.assertIn('Check-In', primary)
        self.assertIn('Clients', primary)
        self.assertNotIn('Billing', primary)
        self.assertNotIn('Settings', primary)


class IntakeWizardTests(TestCase):
    def _base(self, **overrides):
        data = {
            'owner_name': 'Jane Doe',
            'owner_email': 'jane-intake@example.com',
            'owner_phone': '416-555-0100',
            'dog_name': 'Kobe',
            'dog_notes': 'Loves zoomies',
            'vet_clinic_name': 'Grey Street Animal Hospital',
            'vet_clinic_phone': '519-555-0100',
        }
        data.update(overrides)
        return data

    def test_saves_owner_and_dog_without_meet_greet(self):
        form = IntakeWizardForm(data=self._base())
        self.assertTrue(form.is_valid(), form.errors)
        owner, dog, visit = form.save()
        self.assertEqual(owner.owner_name, 'Jane Doe')
        self.assertEqual(dog.dog_name, 'Kobe')
        self.assertEqual(dog.pipeline_stage, ClientProfile.PipelineStage.INQUIRY)
        self.assertEqual(dog.vet_clinic_name, 'Grey Street Animal Hospital')
        self.assertEqual(dog.vet_clinic_phone, '5195550100')
        self.assertIsNone(visit)
        self.assertTrue(dog.feed_secret)

    def test_meet_greet_sets_pipeline_and_visit(self):
        form = IntakeWizardForm(data=self._base(
            meet_greet_start='April 11, 2026 2 pm',
            meet_greet_end='April 11, 2026 3 pm',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        owner, dog, visit = form.save()
        self.assertEqual(dog.pipeline_stage, ClientProfile.PipelineStage.MEET_GREET)
        self.assertIsNotNone(visit)
        self.assertEqual(visit.client_id, dog.pk)
        self.assertIn('Meet & Greet', visit.notes)
        self.assertEqual(timezone.localtime(visit.scheduled_start).hour, 14)

    def test_rejects_dog_name_same_as_owner_first(self):
        form = IntakeWizardForm(data=self._base(dog_name='Jane'))
        self.assertFalse(form.is_valid())
        self.assertIn('dog_name', form.errors)

    def test_rejects_partial_meet_greet(self):
        form = IntakeWizardForm(data=self._base(meet_greet_start='April 11, 2026 2 pm'))
        self.assertFalse(form.is_valid())

    def test_intake_page_loads(self):
        user = get_user_model().objects.create_user(username='david', password='testpass123')
        client = DjangoTestClient()
        client.login(username='david', password='testpass123')
        response = client.get(reverse('operations:client_intake'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Client')
        self.assertContains(response, 'Meet &amp; Greet')
        self.assertContains(response, 'Postal code')
        self.assertContains(response, 'Street')

    def test_capacity_block_creates_nothing(self):
        now = timezone.now()
        start = datetime(2026, 4, 11, 14, 0, tzinfo=TZ)
        end = datetime(2026, 4, 11, 15, 0, tzinfo=TZ)
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Cap{i}',
                owner_name=f'Owner{i}',
                owner_email=f'intake-cap{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=start,
                scheduled_end=end,
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)
        form = IntakeWizardForm(data=self._base(
            meet_greet_start='April 11, 2026 2 pm',
            meet_greet_end='April 11, 2026 3 pm',
        ))
        self.assertFalse(form.is_valid())
        self.assertFalse(CustomerOwner.objects.filter(owner_email='jane-intake@example.com').exists())
        self.assertFalse(ClientProfile.objects.filter(owner_email='jane-intake@example.com').exists())


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
        self.assertTrue(dog.feed_secret)

    def test_form_init_does_not_create_missing_owner(self):
        dog = ClientProfile.objects.create(
            dog_name='Orphan',
            owner_name='Nobody',
            owner_email='orphan-form@example.com',
        )
        form = DogProfileForm(instance=dog)
        self.assertIsNone(form.customer_owner)
        self.assertFalse(
            CustomerOwner.objects.filter(owner_email__iexact='orphan-form@example.com').exists(),
        )

    def test_save_commit_false_still_sets_feed_credentials(self):
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        dog = form.save(commit=False)
        self.assertIsNone(dog.pk)
        self.assertTrue(dog.feed_secret)
        self.assertTrue(dog.feed_dog_slug)
        dog.save()
        stored = ClientProfile.objects.get(pk=dog.pk)
        self.assertEqual(stored.feed_secret, dog.feed_secret)

    def test_edit_without_customer_owner_copies_denormalized_fields(self):
        dog = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
            owner_phone='4165550100',
        )
        self.owner.owner_phone = '5195551234'
        self.owner.save(update_fields=['owner_phone', 'updated_at'])
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': 'updated',
            },
            instance=dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.customer_owner = None
        saved = form.save()
        self.assertEqual(saved.owner_name, 'Jane Doe')
        self.assertEqual(saved.owner_email, 'jane@example.com')
        self.assertEqual(saved.owner_phone, '5195551234')
        self.assertEqual(saved.notes, 'updated')

    def test_save_vet_contacts_on_dog(self):
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'vet_clinic_name': 'Grey Street Animal Hospital',
                'vet_name': 'Dr. Smith',
                'vet_clinic_phone': '519-555-0100',
                'emergency_vet_clinic': 'Emergency Pet Clinic',
                'emergency_vet_phone': '519-555-9999',
                'vet_care_authorization': 'Approve up to $500 triage',
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertTrue(form.is_valid(), form.errors)
        dog = form.save()
        self.assertEqual(dog.vet_clinic_name, 'Grey Street Animal Hospital')
        self.assertEqual(dog.vet_care_authorization, 'Approve up to $500 triage')
        self.assertEqual(dog.vet_clinic_phone, '5195550100')
        self.assertEqual(dog.emergency_vet_phone, '5195559999')

    def test_rejects_invalid_vet_phone(self):
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'vet_clinic_phone': '123',
                'notes': '',
            },
            customer_owner=self.owner,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('vet_clinic_phone', form.errors)

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

    def test_blank_owner_name_does_not_crash_dog_name_clean(self):
        blank_owner = CustomerOwner.objects.create(
            owner_name='   ',
            owner_email='blank-owner@example.com',
        )
        form = DogProfileForm(
            data={
                'dog_name': 'Kobe',
                'pipeline_stage': ClientProfile.PipelineStage.INQUIRY,
                'notes': '',
            },
            customer_owner=blank_owner,
        )
        self.assertTrue(form.is_valid(), form.errors)

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
        self.assertIn('dog_name', form.errors)

    def test_duplicate_dog_name_ignores_surrounding_whitespace(self):
        ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        form = DogProfileForm(
            data={
                'dog_name': '  Kobe  ',
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
        self.assertEqual(updated.owner_phone, '5195551234')

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

    def test_edit_view_updates_dogs_in_one_transaction(self):
        owner = CustomerOwner.objects.create(
            owner_name='Cassia Lewis',
            owner_email='cassia-txn@example.com',
            owner_phone='4165550100',
        )
        dog = ClientProfile.objects.create(
            dog_name='Bo',
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
            owner_phone=owner.owner_phone,
        )
        user = get_user_model().objects.create_user('david-txn', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(
            reverse('operations:customer_edit', args=[owner.pk]),
            {
                'owner_name': 'Cassia Lewis',
                'owner_email': 'cassia-new@example.com',
                'owner_phone': '519-555-1234',
            },
        )
        self.assertEqual(response.status_code, 302)
        owner.refresh_from_db()
        dog.refresh_from_db()
        self.assertEqual(owner.owner_email, 'cassia-new@example.com')
        self.assertEqual(dog.owner_email, 'cassia-new@example.com')
        self.assertEqual(dog.owner_phone, '5195551234')


class CustomerViewsHttpTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')
        self.owner = CustomerOwner.objects.create(
            owner_name='Jane Doe',
            owner_email='jane-http@example.com',
            owner_phone='4165550100',
        )
        self.dog = ClientProfile.objects.create(
            dog_name='Kobe',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
        )

    def test_get_only_views_reject_post(self):
        for url in (
            reverse('operations:client_list'),
            reverse('operations:customer_detail', args=[self.owner.pk]),
            reverse('operations:dog_detail', args=[self.dog.pk]),
            reverse('operations:dog_vaccinations', args=[self.dog.pk]),
            reverse('operations:contact_sync'),
        ):
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 405)

    def test_form_views_reject_put(self):
        for url in (
            reverse('operations:client_create'),
            reverse('operations:customer_edit', args=[self.owner.pk]),
            reverse('operations:dog_edit', args=[self.dog.pk]),
            reverse('operations:customer_add_dog', args=[self.owner.pk]),
            reverse('operations:client_intake'),
            reverse('operations:contact_import_preview'),
        ):
            with self.subTest(url=url):
                response = self.client.put(url)
                self.assertEqual(response.status_code, 405)

    def test_get_only_views_still_load(self):
        response = self.client.get(reverse('operations:client_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse('operations:customer_detail', args=[self.owner.pk]),
        )
        self.assertEqual(response.status_code, 200)

    def test_dog_detail_get_does_not_create_owner(self):
        orphan = ClientProfile.objects.create(
            dog_name='Orphan',
            owner_name='Nobody',
            owner_email='orphan-get@example.com',
        )
        response = self.client.get(reverse('operations:dog_detail', args=[orphan.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            CustomerOwner.objects.filter(owner_email__iexact='orphan-get@example.com').exists(),
        )
        orphan.refresh_from_db()
        self.assertFalse(orphan.feed_secret)

    def test_invalid_stage_query_is_ignored(self):
        response = self.client.get(
            reverse('operations:client_list'),
            {'stage': 'not-a-stage'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_stage'], '')
        self.assertContains(response, self.dog.dog_name)

    def test_vcard_filename_strips_unsafe_characters(self):
        self.dog.dog_name = 'Mr. Biscuit/One'
        self.dog.save(update_fields=['dog_name', 'updated_at'])
        response = self.client.get(reverse('operations:client_vcard', args=[self.dog.pk]))
        self.assertEqual(response.status_code, 200)
        disposition = response['Content-Disposition']
        self.assertIn('filename="', disposition)
        filename = disposition.split('filename="')[1].rstrip('"')
        self.assertTrue(filename.endswith('.vcf'))
        stem = filename[:-4]
        self.assertRegex(stem, r'^[A-Za-z0-9_-]+$')
        self.assertEqual(stem, 'Mr__Biscuit_One_Jane_Doe')

    def test_import_selected_ignores_non_integer_rows(self):
        session = self.client.session
        session['contact_import_analysis'] = {'selectable_contacts': []}
        session.save()
        response = self.client.post(
            reverse('operations:contact_import_selected'),
            {'selected_rows': ['nope', 'x']},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('operations:contact_import_preview'))

    def test_advance_pipeline_noops_when_already_approved(self):
        self.dog.pipeline_stage = ClientProfile.PipelineStage.APPROVED
        self.dog.save(update_fields=['pipeline_stage', 'updated_at'])
        response = self.client.post(
            reverse('operations:advance_pipeline', args=[self.dog.pk]),
            follow=True,
        )
        self.dog.refresh_from_db()
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.APPROVED)
        self.assertContains(response, 'already')

    def test_advance_pipeline_moves_inquiry_forward(self):
        response = self.client.post(
            reverse('operations:advance_pipeline', args=[self.dog.pk]),
            follow=True,
        )
        self.dog.refresh_from_db()
        self.assertEqual(
            self.dog.pipeline_stage,
            ClientProfile.PipelineStage.MEET_GREET,
        )
        self.assertContains(response, 'Meet')

    def test_orphan_dog_appears_on_client_list(self):
        orphan = ClientProfile.objects.create(
            dog_name='Stray',
            owner_name='Lost Owner',
            owner_email='stray-list@example.com',
        )
        response = self.client.get(reverse('operations:client_list'))
        self.assertContains(response, 'Dogs without a customer')
        self.assertContains(response, 'Stray')
        self.assertContains(response, 'stray-list@example.com')
        self.assertContains(response, reverse('operations:dog_create_customer', args=[orphan.pk]))

    def test_create_customer_from_orphan_dog(self):
        orphan = ClientProfile.objects.create(
            dog_name='Stray',
            owner_name='Lost Owner',
            owner_email='stray-create@example.com',
        )
        response = self.client.post(
            reverse('operations:dog_create_customer', args=[orphan.pk]),
        )
        self.assertEqual(response.status_code, 302)
        owner = CustomerOwner.objects.get(owner_email='stray-create@example.com')
        self.assertEqual(owner.owner_name, 'Lost Owner')
        self.assertEqual(
            response.url,
            reverse('operations:customer_detail', args=[owner.pk]),
        )

    def test_hide_removes_dog_from_client_list_not_database(self):
        response = self.client.post(reverse('operations:dog_hide', args=[self.dog.pk]))
        self.assertEqual(response.status_code, 302)
        self.dog.refresh_from_db()
        self.assertTrue(self.dog.is_hidden)
        self.assertTrue(ClientProfile.objects.filter(pk=self.dog.pk).exists())
        customer_page = self.client.get(
            reverse('operations:customer_detail', args=[self.owner.pk]),
        )
        self.assertContains(customer_page, 'Hidden dogs')
        self.assertContains(customer_page, self.dog.dog_name)
        list_page = self.client.get(reverse('operations:client_list'))
        self.assertNotContains(list_page, f'class="title">{self.dog.dog_name}<')

    def test_unhide_returns_dog_to_client_list(self):
        self.dog.hide()
        response = self.client.post(reverse('operations:dog_unhide', args=[self.dog.pk]))
        self.assertEqual(response.status_code, 302)
        self.dog.refresh_from_db()
        self.assertFalse(self.dog.is_hidden)
        list_page = self.client.get(reverse('operations:client_list'))
        self.assertContains(list_page, self.dog.dog_name)

    def test_legacy_delete_url_hides_instead_of_deleting(self):
        self.client.post(reverse('operations:dog_delete', args=[self.dog.pk]))
        self.assertTrue(ClientProfile.objects.filter(pk=self.dog.pk).exists())
        self.dog.refresh_from_db()
        self.assertTrue(self.dog.is_hidden)


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
        dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
        dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
        dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
        dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
        dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
        self.dog = _ready_for_standard_stay(ClientProfile.objects.create(
            dog_name='Winston',
            owner_name='Alexa Green',
            owner_email='alexagreen4@outlook.com',
        ))

    def test_create_visit_from_natural_language(self):
        form = VisitForm(
            data={
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
            'business_service': _default_service_pk(),
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
        with patch('operations.models.scheduling.check_visit_capacity') as mock_capacity:
            visits = form.save_all()
        self.assertEqual(len(visits), 5)
        mock_capacity.assert_not_called()


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

    @override_settings(PUBLIC_SITE_URL='https://happywaffle.ngrok.app')
    def test_format_confirmation_includes_feed_url_when_public_site_set(self):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        self.dog.ensure_feed_credentials()
        _, body = format_booking_confirmation(self.dog, [visit])
        self.assertIn('photo feed anytime', body)
        self.assertIn(f'/feed/{self.dog.feed_secret}/winston/', body)
        self.assertIn('https://happywaffle.ngrok.app/feed/', body)

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

    def test_dog_detail_offers_send_email_when_unsent(self):
        CustomerOwner.ensure_for_client(self.dog)
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-email', 'e@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'Send email')
        self.assertContains(
            response,
            reverse('operations:visit_send_confirmation', args=[visit.pk]),
        )
        self.assertNotContains(response, 'emailed')

    def test_dog_detail_shows_emailed_date_when_sent(self):
        CustomerOwner.ensure_for_client(self.dog)
        Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            confirmation_email_sent_at=datetime(2026, 4, 10, 12, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-emailed', 'e2@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, 'emailed Apr 10')
        self.assertNotContains(response, 'Send email')

    @patch('operations.views.scheduling.visits.send_booking_confirmation')
    def test_send_confirmation_view_calls_email(self, mock_send):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-send', 'e3@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(
            reverse('operations:visit_send_confirmation', args=[visit.pk]),
        )
        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        self.assertEqual(args[0], self.dog)
        self.assertEqual(list(args[1]), [visit])

    @patch('operations.views.scheduling.visits.send_booking_confirmation')
    def test_send_confirmation_view_skips_if_already_sent(self, mock_send):
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 13, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 11, 18, 0, tzinfo=TZ),
            confirmation_email_sent_at=datetime(2026, 4, 10, 12, 0, tzinfo=TZ),
        )
        user = get_user_model().objects.create_user('david-skip', 'e4@example.com', 'pass')
        self.client.force_login(user)
        self.client.post(reverse('operations:visit_send_confirmation', args=[visit.pk]))
        mock_send.assert_not_called()


@override_settings(GMAIL_OAUTH_DIR=Path('/nonexistent/oauth-dir'))
class GmailSendTests(TestCase):
    def test_send_gmail_requires_token(self):
        with self.assertRaises(GmailSendError) as ctx:
            send_gmail('Subject', 'Body', 'test@example.com')
        self.assertIn('oauth_setup.py', str(ctx.exception))

    @patch('operations.services.gmail_send._credentials_path')
    @patch('operations.services.gmail_send._token_path')
    @patch('operations.services.gmail_send.Credentials')
    def test_refresh_error_becomes_gmail_send_error(self, mock_creds_cls, mock_token, mock_creds_path):
        from google.auth.exceptions import RefreshError

        mock_token.return_value.exists.return_value = True
        mock_creds_path.return_value.exists.return_value = False
        creds = MagicMock()
        creds.expired = True
        creds.refresh_token = 'rt'
        creds.refresh.side_effect = RefreshError('invalid_grant: Bad Request')
        mock_creds_cls.from_authorized_user_file.return_value = creds
        with self.assertRaises(GmailSendError) as ctx:
            _load_credentials()
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

        with patch('operations.models.scheduling.calculate_fee') as mock_fee:
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
        with patch('operations.models.scheduling.calculate_fee') as mock_fee:
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
        from operations.capacity import _day_bounds

        start, end = _day_bounds(date(2026, 4, 10))
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

    def test_naive_datetimes_do_not_crash_capacity(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0),
            scheduled_end=datetime(2026, 4, 11, 17, 0),
        )
        start_day, end_day = _capacity_span_dates(visit)
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
        start_day, end_day = _capacity_span_dates(visit)
        self.assertEqual(start_day, date(2026, 4, 11))
        self.assertEqual(end_day, date(2026, 4, 11))

    def test_end_just_after_midnight_includes_next_day(self):
        visit = Visit(
            client=self.dog,
            scheduled_start=datetime(2026, 4, 11, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 4, 12, 0, 1, tzinfo=TZ),
        )
        _, end_day = _capacity_span_dates(visit)
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


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='david',
            password='testpass123',
        )
        self.client = DjangoTestClient()
        self.client.login(username='david', password='testpass123')

    def test_dashboard_loads(self):
        response = self.client.get(reverse('operations:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dad4dogs')

    def test_dashboard_rejects_huge_year(self):
        today = timezone.localdate()
        response = self.client.get(
            reverse('operations:dashboard'),
            {'year': '999999', 'month': '1'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cal_year'], today.year)
        self.assertEqual(response.context['cal_month'], today.month)

    def test_dashboard_rejects_year_zero(self):
        today = timezone.localdate()
        response = self.client.get(
            reverse('operations:dashboard'),
            {'year': '0', 'month': '6'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cal_year'], today.year)

    def test_dashboard_rejects_post(self):
        response = self.client.post(reverse('operations:dashboard'))
        self.assertEqual(response.status_code, 405)

    def test_parse_datetime_rejects_post(self):
        response = self.client.post(reverse('operations:parse_datetime'))
        self.assertEqual(response.status_code, 405)

    def test_visit_create_rejects_put(self):
        dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        response = self.client.put(
            reverse('operations:visit_create', args=[dog.pk]),
        )
        self.assertEqual(response.status_code, 405)


class PendingEventApproveTests(TestCase):
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
        self.start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        self.end = datetime(2026, 3, 10, 17, 0, tzinfo=TZ)

    def test_approve_creates_visit(self):
        event = PendingCalendarEvent.objects.create(
            event_uid='uid-ok',
            summary='Rex boarding',
            start_datetime=self.start,
            end_datetime=self.end,
            matched_client=self.dog,
        )
        response = self.client.post(
            reverse('operations:approve_pending_event', args=[event.pk]),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.review_status, PendingCalendarEvent.ReviewStatus.APPROVED)
        self.assertTrue(
            Visit.objects.filter(client=self.dog, scheduled_start=self.start).exists(),
        )

    def test_approve_capacity_block_keeps_event_pending(self):
        now = timezone.now()
        extra = []
        for i in range(INSURANCE_CEILING):
            dog = ClientProfile.objects.create(
                dog_name=f'Dog{i}',
                owner_name=f'Owner{i}',
                owner_email=f'cap{i}@example.com',
            )
            extra.append(Visit(
                client=dog,
                scheduled_start=self.start,
                scheduled_end=self.end,
                created_at=now,
                updated_at=now,
            ))
        Visit.objects.bulk_create(extra)
        event = PendingCalendarEvent.objects.create(
            event_uid='uid-full',
            summary='One more dog',
            start_datetime=self.start,
            end_datetime=self.end,
            matched_client=self.dog,
        )
        response = self.client.post(
            reverse('operations:approve_pending_event', args=[event.pk]),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.review_status, PendingCalendarEvent.ReviewStatus.PENDING)
        self.assertFalse(Visit.objects.filter(client=self.dog).exists())


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


def _test_image_file(name='moment.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (1200, 900), color=(34, 139, 34)).save(buffer, format='JPEG')
    buffer.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, buffer.read(), content_type='image/jpeg')


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

    def test_rejects_camera_and_gallery_together(self):
        form = TimelineMomentForm(
            data={'caption_notes': 'Two photos', 'visit_ids': [str(self.visit.pk)]},
            files={
                'photo_camera': _test_image_file('cam.jpg'),
                'photo_gallery': _test_image_file('gal.jpg'),
            },
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('not both', str(form.errors).lower())

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
        self.assertEqual(form.cleaned_data['latitude'], Decimal('43.0'))
        self.assertEqual(form.cleaned_data['longitude'], Decimal('-81.2'))

    def test_blank_coordinates_are_allowed(self):
        form = TimelineMomentForm(
            data={'caption_notes': '', 'visit_ids': [str(self.visit.pk)]},
            files={'photo_gallery': _test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['latitude'], '')
        self.assertEqual(form.cleaned_data['longitude'], '')

    def test_rejects_non_numeric_coordinates(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': 'north',
                'longitude': '-81.2',
            },
            files={'photo_gallery': _test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('latitude', form.errors)

    def test_rejects_out_of_range_coordinates(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': '91',
                'longitude': '-81.2',
            },
            files={'photo_gallery': _test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('latitude', form.errors)

    def test_rejects_latitude_without_longitude(self):
        form = TimelineMomentForm(
            data={
                'caption_notes': '',
                'visit_ids': [str(self.visit.pk)],
                'latitude': '43.0',
            },
            files={'photo_gallery': _test_image_file()},
            eligible_visits=Visit.objects.filter(pk=self.visit.pk),
        )
        self.assertFalse(form.is_valid())
        self.assertIn('longitude', form.errors)


class VisitTimelineTests(TestCase):
    def setUp(self):
        # active_checked_in_visits() scopes to local "today"; freeze to visit day.
        self._today_patch = patch(
            'operations.services.timeline_visits.timezone.localdate',
            return_value=date(2026, 7, 6),
        )
        self._today_patch.start()
        self.addCleanup(self._today_patch.stop)
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

    def test_timeline_get_does_not_query_forward_targets_per_event(self):
        for caption in ('One', 'Two', 'Three'):
            log_moment_for_visits(
                visits=[self.visit],
                media_kind='photo',
                uploaded_file=_test_image_file(),
                caption_notes=caption,
                latitude=Decimal('43.01'),
                longitude=Decimal('-81.23'),
                used_fallback=False,
                fallback_label='',
            )
        with patch('operations.views.scheduling.timeline.visits_available_for_forward') as mock_fwd:
            response = self.client.get(
                reverse('operations:visit_timeline', args=[self.visit.pk]),
            )
        self.assertEqual(response.status_code, 200)
        mock_fwd.assert_not_called()

    def test_invalid_moment_flashes_plain_error(self):
        from django.contrib.messages import get_messages

        response = self.client.post(
            reverse('operations:visit_timeline', args=[self.visit.pk]),
            {'caption_notes': '', 'visit_ids': [str(self.visit.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        text = ' '.join(str(m) for m in get_messages(response.wsgi_request))
        self.assertNotIn('*', text)
        self.assertNotIn('visit_ids', text)
        self.assertTrue(text)
        self.assertRegex(text.lower(), r'photo|video|capture')

    def test_invalid_forward_flashes_plain_error(self):
        from django.contrib.messages import get_messages

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
            {},
        )
        self.assertEqual(response.status_code, 302)
        text = ' '.join(str(m) for m in get_messages(response.wsgi_request))
        self.assertNotIn('*', text)
        self.assertNotIn('visit_ids', text)
        self.assertIn('Share with', text)

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
        self.assertRegex(
            asset.photo_high_res.name,
            r'^timeline/assets/\d{4}/\d{2}/\d{2}/master_.+\.jpg$',
        )
        self.assertNotIn('/new/', asset.photo_high_res.name)
        self.assertRegex(
            asset.photo_thumbnail.name,
            r'^timeline/assets/\d{4}/\d{2}/\d{2}/thumb_.+\.webp$',
        )

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


class TimelineUploadPathTests(TestCase):
    def test_uses_captured_at_date_not_pk_or_new(self):
        class Dummy:
            pk = None
            captured_at = datetime(2026, 8, 23, 15, 0, tzinfo=TZ)

        path = timeline_asset_upload_path(Dummy(), 'master_abc.jpg')
        self.assertEqual(path, 'timeline/assets/2026/08/23/master_abc.jpg')

    def test_falls_back_to_now_when_captured_at_missing(self):
        class Dummy:
            pk = None
            captured_at = None

        frozen = datetime(2026, 1, 2, 12, 0, tzinfo=TZ)
        with patch('operations.models.scheduling.timezone.now', return_value=frozen):
            path = timeline_asset_upload_path(Dummy(), 'thumb.webp')
        self.assertEqual(path, 'timeline/assets/2026/01/02/thumb.webp')
        self.assertNotIn('/new/', path)


class TimelineMediaAssetCapturedAtTests(TestCase):
    def setUp(self):
        dog = ClientProfile.objects.create(
            dog_name='Rex',
            owner_name='Jane Doe',
            owner_email='jane@example.com',
        )
        self.visit = Visit.objects.create(
            client=dog,
            scheduled_start=datetime(2026, 8, 23, 9, 0, tzinfo=TZ),
            scheduled_end=datetime(2026, 8, 23, 17, 0, tzinfo=TZ),
        )

    def _create(self, **kwargs):
        defaults = {
            'media_type': TimelineMediaAsset.MediaType.PHOTO,
            'latitude': Decimal('43.01'),
            'longitude': Decimal('-81.23'),
            'original_visit': self.visit,
        }
        defaults.update(kwargs)
        return TimelineMediaAsset.objects.create(**defaults)

    def test_captured_at_defaults_when_omitted(self):
        before = timezone.now()
        asset = self._create()
        after = timezone.now()
        self.assertIsNotNone(asset.captured_at)
        self.assertGreaterEqual(asset.captured_at, before)
        self.assertLessEqual(asset.captured_at, after)

    def test_explicit_captured_at_is_kept(self):
        when = datetime(2026, 4, 11, 9, 0, tzinfo=TZ)
        asset = self._create(captured_at=when)
        asset.refresh_from_db()
        self.assertEqual(asset.captured_at, when)


class FeedSlugTests(TestCase):
    def test_dog_slug_from_name(self):
        self.assertEqual(dog_slug_from_name('Lulu'), 'lulu')
        self.assertEqual(dog_slug_from_name('Mr. Biscuit'), 'mr-biscuit')

    def test_generate_feed_secret_is_speakable(self):
        consonants = set('bcdfghjklmnprstvwz')
        vowels = set('aeiou')
        secret = generate_feed_secret()
        self.assertGreaterEqual(len(secret), 8)
        self.assertTrue(secret.isalpha())
        self.assertEqual(secret, secret.lower())
        for index, char in enumerate(secret):
            if index % 2 == 0:
                self.assertIn(char, consonants)
            else:
                self.assertIn(char, vowels)

    def test_ensure_feed_credentials_on_client(self):
        dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        dog.ensure_feed_credentials()
        self.assertTrue(dog.feed_secret)
        self.assertEqual(dog.feed_dog_slug, 'lulu')
        self.assertIn('/feed/', dog.feed_url_path())

    def test_regenerate_feed_secret_changes_link(self):
        dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        dog.ensure_feed_credentials()
        old_secret = dog.feed_secret
        dog.regenerate_feed_secret()
        self.assertNotEqual(dog.feed_secret, old_secret)
        self.assertEqual(dog.feed_dog_slug, 'lulu')


class CustomerFeedTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        self.dog.ensure_feed_credentials()
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=timezone.now(),
            scheduled_end=timezone.now() + timedelta(hours=4),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=timezone.now(),
        )
        self.client = DjangoTestClient()

    def test_customer_feed_requires_matching_dog_slug(self):
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': 'wrong-dog',
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_customer_feed_sets_visitor_cookie_and_logs_access(self):
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Lulu', response.content.decode())
        self.assertNotIn('bottom-nav', response.content.decode())
        self.assertEqual(response.headers.get('X-Robots-Tag'), 'noindex, nofollow')
        self.assertIn(VISITOR_COOKIE_NAME, response.cookies)
        from operations.models import FeedAccessLog
        self.assertEqual(FeedAccessLog.objects.filter(client=self.dog).count(), 1)

    def test_customer_feed_shows_timeline_event(self):
        _, events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=_test_image_file(),
            caption_notes='Sunny nap',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.assertEqual(len(events), 1)
        url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(url)
        self.assertContains(response, 'Sunny nap')
        self.assertNotIn('-81.23', response.content.decode())


class FeedInteractionTests(TestCase):
    def setUp(self):
        self.dog = ClientProfile.objects.create(
            dog_name='Lulu',
            owner_name='Jane',
            owner_email='jane@example.com',
        )
        self.dog.ensure_feed_credentials()
        self.visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=timezone.now(),
            scheduled_end=timezone.now() + timedelta(hours=4),
            status=Visit.Status.CHECKED_IN,
            actual_arrival=timezone.now(),
        )
        _, self.events = log_moment_for_visits(
            visits=[self.visit],
            media_kind='photo',
            uploaded_file=_test_image_file(),
            caption_notes='Nap time',
            latitude=Decimal('43.01'),
            longitude=Decimal('-81.23'),
            used_fallback=False,
            fallback_label='',
        )
        self.asset_id = self.events[0].media_asset_id
        self.client = DjangoTestClient()

    def _feed_react_url(self):
        return reverse(
            'operations:customer_feed_react',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )

    def test_react_and_comment_on_feed(self):
        self.client.post(self._feed_react_url(), {'emoji': MediaReaction.Emoji.LOVE})
        self.assertEqual(MediaReaction.objects.count(), 1)
        comment_url = reverse(
            'operations:customer_feed_comment',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )
        self.client.post(comment_url, {'display_name': 'Mom', 'text': 'So cute!'})
        self.assertEqual(MediaComment.objects.count(), 1)
        feed_url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(feed_url)
        self.assertContains(response, 'So cute!')
        self.assertContains(response, '❤️')  # standard emoji in reaction summary

    def test_public_share_link_isolated_from_feed(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        self.assertTrue(link.share_token)
        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        self.assertIn('/feed/share/', share_url)
        response = self.client.get(share_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lulu')
        self.assertNotIn('icon-192.png', response.content.decode())
        self.assertContains(response, 'og:image')
        self.assertContains(response, 'twitter:image')
        self.assertNotIn(self.dog.feed_secret, response.content.decode())
        self.assertContains(response, 'share-icon-btn')
        self.assertContains(response, 'comment-icon-btn')
        self.assertContains(response, 'download-icon-btn')
        self.assertContains(response, '/download/')
        self.assertContains(response, f'dad4dogs_{link.id}.jpg')
        self.assertContains(response, 'reaction-bar')
        self.assertNotContains(response, 'comment-panel always-open')
        link.refresh_from_db()
        self.assertEqual(link.view_count, 1)

    def test_public_share_download_filename(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        download_url = reverse(
            'operations:public_feed_share_download',
            kwargs={'share_token': link.share_token},
        )
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        disposition = response.headers.get('Content-Disposition', '')
        self.assertIn('attachment', disposition)
        self.assertIn(f'dad4dogs_{link.id}.jpg', disposition)
        self.assertNotIn('master_', disposition)

    def test_public_share_react_without_comment(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        react_url = reverse(
            'operations:public_feed_share_react',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LOVE})
        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        response = self.client.get(share_url)
        self.assertContains(response, '❤️')
        self.assertEqual(MediaComment.objects.count(), 0)

    def test_public_share_react_and_comment(self):
        link = get_or_create_share_link(client=self.dog, asset_id=self.asset_id)
        react_url = reverse(
            'operations:public_feed_share_react',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LOVE})
        self.assertEqual(MediaReaction.objects.count(), 1)

        comment_url = reverse(
            'operations:public_feed_share_comment',
            kwargs={'share_token': link.share_token},
        )
        self.client.post(comment_url, {'display_name': 'Friend', 'text': 'Adorable!'})
        self.assertEqual(MediaComment.objects.count(), 1)

        link.refresh_from_db()
        views_before = link.view_count
        self.client.post(react_url, {'emoji': MediaReaction.Emoji.LIKE})
        link.refresh_from_db()
        self.assertEqual(link.view_count, views_before)

        share_url = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
        response = self.client.get(share_url)
        self.assertContains(response, 'Adorable!')
        self.assertContains(response, '❤️')
        self.assertContains(response, 'Friend')
        link.refresh_from_db()
        self.assertEqual(link.view_count, views_before + 1)

    def test_customer_feed_has_compact_share_icon(self):
        feed_url = reverse(
            'operations:customer_feed',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
            },
        )
        response = self.client.get(feed_url)
        self.assertContains(response, 'share-icon-btn')
        self.assertContains(response, 'comment-icon-btn')
        self.assertContains(response, '/feed/share/')
        self.assertNotContains(response, 'Share this moment with friends')
        self.assertContains(response, '🐾')

    def test_checkin_feed_activity_requires_login(self):
        url = reverse('operations:checkin_feed_activity')
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_checkin_feed_activity_returns_comment(self):
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        comment_url = reverse(
            'operations:customer_feed_comment',
            kwargs={
                'feed_secret': self.dog.feed_secret,
                'feed_dog_slug': self.dog.feed_dog_slug,
                'asset_id': self.asset_id,
            },
        )
        self.client.post(comment_url, {'display_name': 'Mom', 'text': 'Love this!'})
        activity_url = reverse('operations:checkin_feed_activity')
        response = self.client.get(activity_url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        dog_bucket = payload['dogs'][str(self.dog.pk)]
        self.assertEqual(dog_bucket['dog_name'], 'Lulu')
        self.assertTrue(any(item['text'] == 'Love this!' for item in dog_bucket['items']))

