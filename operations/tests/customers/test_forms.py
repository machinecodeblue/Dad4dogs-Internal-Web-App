from django.test import TestCase

from operations.forms import CustomerOwnerForm, DogProfileForm
from operations.models import ClientProfile, CustomerOwner


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