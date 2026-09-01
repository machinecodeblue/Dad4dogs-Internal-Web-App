from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.forms import CustomerOwnerForm, DogProfileForm
from operations.models import ClientProfile, CustomerOwner, VaccinationRecord


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
        self.assertContains(response, '<summary>Stage management &amp; more</summary>')
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
        primary = html.split('app-primary-nav', 1)[1].split('</nav>', 1)[0]
        self.assertIn('Check-In', primary)
        self.assertIn('Clients', primary)
        self.assertNotIn('Billing', primary)
        self.assertNotIn('Settings', primary)


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