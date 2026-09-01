from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient, TestCase
from django.urls import reverse
from django.utils import timezone

from operations.capacity import INSURANCE_CEILING
from operations.forms import IntakeWizardForm, VisitForm
from operations.models import (
    BusinessService,
    ClientProfile,
    CustomerOwner,
    VaccinationRecord,
    Visit,
)
from operations.tests.conftest import TZ


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

    def test_intake_wizard_assigns_meet_greet_service(self):
        form = IntakeWizardForm(data=self._base(
            meet_greet_start='April 11, 2026 2 pm',
            meet_greet_end='April 11, 2026 2:15 pm',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        _, _, visit = form.save()
        self.assertIsNotNone(visit.business_service_id)
        self.assertEqual(visit.business_service.slug, 'meet_greet')
        self.assertTrue(visit.business_service.capacity_exempt)
        self.assertEqual(visit.business_service.base_rate, Decimal('0.00'))

    def test_intake_wizard_defaults_fifteen_minutes(self):
        form = IntakeWizardForm(data=self._base(
            meet_greet_start='April 11, 2026 2 pm',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        _, _, visit = form.save()
        start = timezone.localtime(visit.scheduled_start)
        end = timezone.localtime(visit.scheduled_end)
        self.assertEqual((end - start).total_seconds(), 15 * 60)

    def test_rejects_dog_name_same_as_owner_first(self):
        form = IntakeWizardForm(data=self._base(dog_name='Jane'))
        self.assertFalse(form.is_valid())
        self.assertIn('dog_name', form.errors)

    def test_rejects_end_without_start(self):
        form = IntakeWizardForm(data=self._base(meet_greet_end='April 11, 2026 2:15 pm'))
        self.assertFalse(form.is_valid())
        self.assertIn('meet_greet_start', form.errors)

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
        self.assertContains(response, '15 minutes')

    def test_intake_wizard_succeeds_when_facility_at_capacity(self):
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
            meet_greet_end='April 11, 2026 2:15 pm',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        owner, dog, visit = form.save()
        self.assertIsNotNone(visit)
        self.assertEqual(visit.business_service.slug, 'meet_greet')
        self.assertTrue(CustomerOwner.objects.filter(owner_email='jane-intake@example.com').exists())
        self.assertEqual(dog.pipeline_stage, ClientProfile.PipelineStage.MEET_GREET)

    def test_meet_greet_checkout_fee_is_zero(self):
        form = IntakeWizardForm(data=self._base(
            meet_greet_start='April 11, 2026 2 pm',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        _, _, visit = form.save()
        arrival = visit.scheduled_start
        departure = visit.scheduled_end
        with patch('operations.models.scheduling.visits.timezone.now') as mock_now:
            mock_now.return_value = arrival
            visit.check_in()
            mock_now.return_value = departure
            visit.check_out()
        visit.refresh_from_db()
        self.assertEqual(visit.calculated_fee, Decimal('0.00'))
        self.assertEqual(visit.fee_breakdown[0]['amount'], '0.00')
        self.assertEqual(visit.fee_breakdown[0]['service_slug'], 'meet_greet')


class PipelinePhase2Tests(TestCase):
    def setUp(self):
        from operations.services.context_tenant import get_active_workspace
        from operations.services.pipeline import INITIAL_EVALUATION_SLUG, MEET_GREET_SLUG

        self.workspace = get_active_workspace()
        self.meet = BusinessService.objects.get(tenant=self.workspace, slug=MEET_GREET_SLUG)
        self.evaluation = BusinessService.objects.get(
            tenant=self.workspace,
            slug=INITIAL_EVALUATION_SLUG,
        )
        self.owner = CustomerOwner.objects.create(
            owner_name='Eval Owner',
            owner_email='eval-phase2@example.com',
            owner_phone='4165550199',
        )
        self.dog = ClientProfile.objects.create(
            dog_name='Pip',
            owner_name=self.owner.owner_name,
            owner_email=self.owner.owner_email,
            owner_phone=self.owner.owner_phone,
            pipeline_stage=ClientProfile.PipelineStage.MEET_GREET,
        )

    def _complete_meet_greet(self):
        start = datetime(2026, 5, 1, 14, 0, tzinfo=TZ)
        end = datetime(2026, 5, 1, 14, 15, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            business_service=self.meet,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            calculated_fee=Decimal('0.00'),
            fee_breakdown=[{'tier': 'Meet & Greet', 'amount': '0.00', 'service_slug': 'meet_greet'}],
            notes='Meet & Greet — intake',
        )
        return visit

    def _papers_ready(self):
        self.owner.mark_coi_received()
        VaccinationRecord.objects.create(
            client=self.dog,
            expires_at=timezone.localdate() + timedelta(days=180),
            validated=True,
        )

    def test_evaluation_blockers_without_papers_and_pass(self):
        blockers = self.dog.evaluation_stay_blockers()
        self.assertTrue(any('Evaluation' in b or 'Meet & Greet' in b for b in blockers))

    def _pass_meet_greet(self, visit=None):
        from operations.services.pipeline import apply_meet_greet_outcome
        visit = visit or self._complete_meet_greet()
        apply_meet_greet_outcome(
            visit,
            outcome=Visit.MeetGreetOutcome.PASS,
            notes='Good fit — continue to paperwork.',
        )
        self.dog.refresh_from_db()
        return visit

    def test_schedule_meet_greet_from_existing_dog(self):
        from operations.forms.intake import MeetGreetScheduleForm

        form = MeetGreetScheduleForm(
            data={'start_at': 'May 1, 2026 2 pm', 'notes': ''},
            dog=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visit = form.save()
        self.assertEqual(visit.business_service.slug, 'meet_greet')
        self.assertEqual(
            (visit.scheduled_end - visit.scheduled_start).total_seconds(),
            15 * 60,
        )

    def test_visit_form_rejects_meet_greet_service(self):
        form = VisitForm(
            data={
                'start_at': 'May 1, 2026 2 pm',
                'end_at': 'May 1, 2026 2:15 pm',
                'business_service': self.meet.pk,
                'notes': '',
                'repeat_frequency': 'none',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())

    def test_dog_detail_links_dedicated_meet_greet_url(self):
        user = get_user_model().objects.create_user('david2', 'd2@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertContains(response, reverse('operations:schedule_meet_greet', args=[self.dog.pk]))
        self.assertNotContains(response, f'/dogs/{self.dog.pk}/visits/add/?service=meet_greet')

    def test_meet_greet_outcome_pass_advances(self):
        visit = self._complete_meet_greet()
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(
            reverse('operations:meet_greet_outcome', args=[visit.pk]),
            {
                'meet_greet_notes': 'Owner engaged; dog friendly.',
                'meet_greet_outcome': Visit.MeetGreetOutcome.PASS,
            },
        )
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.dog.refresh_from_db()
        self.assertEqual(visit.meet_greet_outcome, Visit.MeetGreetOutcome.PASS)
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.EVALUATION)

    def test_meet_greet_decline_blocks_evaluation(self):
        from operations.services.pipeline import apply_meet_greet_outcome
        visit = self._complete_meet_greet()
        apply_meet_greet_outcome(
            visit,
            outcome=Visit.MeetGreetOutcome.DECLINE,
            notes='Not a fit for the pack.',
        )
        self.dog.refresh_from_db()
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.MEET_GREET)
        self.assertTrue(self.dog.evaluation_stay_blockers())

    def test_evaluation_schedule_allowed_when_ready(self):
        from operations.forms.intake import EvaluationScheduleForm

        self._pass_meet_greet()
        self._papers_ready()
        form = EvaluationScheduleForm(
            data={'start_at': 'May 10, 2026 10 am', 'notes': ''},
            dog=self.dog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        visit = form.save()
        self.assertEqual(visit.business_service.slug, 'initial_evaluation')
        self.assertEqual(
            (visit.scheduled_end - visit.scheduled_start).total_seconds(),
            4 * 3600,
        )

    def test_visit_form_boarding_blocked_before_approved(self):
        self._pass_meet_greet()
        self._papers_ready()
        boarding = BusinessService.objects.get(tenant=self.workspace, slug='short_visit')
        form = VisitForm(
            data={
                'start_at': 'May 10, 2026 10 am',
                'end_at': 'May 10, 2026 11 am',
                'business_service': boarding.pk,
                'notes': '',
                'repeat_frequency': 'none',
            },
            client=self.dog,
        )
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_evaluation_outcome_approve(self):
        self._pass_meet_greet()
        self._papers_ready()
        start = datetime(2026, 5, 10, 10, 0, tzinfo=TZ)
        end = datetime(2026, 5, 10, 14, 0, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            business_service=self.evaluation,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            calculated_fee=Decimal('15.00'),
            fee_breakdown=[{'tier': 'Initial Evaluation', 'amount': '15.00', 'service_slug': 'initial_evaluation'}],
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(
            reverse('operations:evaluation_outcome', args=[visit.pk]),
            {
                'evaluation_notes': 'Calm in the pack, good recall.',
                'evaluation_outcome': Visit.EvaluationOutcome.APPROVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.dog.refresh_from_db()
        self.assertEqual(visit.evaluation_outcome, Visit.EvaluationOutcome.APPROVE)
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.APPROVED)

    def test_evaluation_checkout_redirects_to_outcome(self):
        self._pass_meet_greet()
        self._papers_ready()
        start = datetime(2026, 5, 10, 10, 0, tzinfo=TZ)
        end = datetime(2026, 5, 10, 14, 0, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            business_service=self.evaluation,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.CHECKED_IN,
            actual_arrival=start,
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        with patch('operations.models.scheduling.visits.timezone.now') as mock_now:
            mock_now.return_value = end
            response = self.client.post(reverse('operations:visit_check_out', args=[visit.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('operations:evaluation_outcome', args=[visit.pk]))

    def test_meet_greet_checkout_redirects_to_outcome(self):
        start = datetime(2026, 5, 1, 14, 0, tzinfo=TZ)
        end = datetime(2026, 5, 1, 14, 15, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            business_service=self.meet,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.CHECKED_IN,
            actual_arrival=start,
        )
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        with patch('operations.models.scheduling.visits.timezone.now') as mock_now:
            mock_now.return_value = end
            response = self.client.post(reverse('operations:visit_check_out', args=[visit.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('operations:meet_greet_outcome', args=[visit.pk]))

    def test_evaluation_further_keeps_evaluation_stage(self):
        self._pass_meet_greet()
        self._papers_ready()
        from operations.services.pipeline import apply_evaluation_outcome
        start = datetime(2026, 5, 10, 10, 0, tzinfo=TZ)
        end = datetime(2026, 5, 10, 14, 0, tzinfo=TZ)
        visit = Visit.objects.create(
            client=self.dog,
            business_service=self.evaluation,
            scheduled_start=start,
            scheduled_end=end,
            status=Visit.Status.COMPLETED,
            actual_arrival=start,
            actual_departure=end,
            calculated_fee=Decimal('15.00'),
        )
        apply_evaluation_outcome(
            visit,
            outcome=Visit.EvaluationOutcome.FURTHER,
            notes='Needs another short pack session.',
        )
        self.dog.refresh_from_db()
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.EVALUATION)

    def test_dog_detail_stale_meet_greet_offers_schedule(self):
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[self.dog.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Intake pipeline')
        self.assertContains(response, 'Schedule Meet &amp; Greet')
        self.assertContains(response, reverse('operations:schedule_meet_greet', args=[self.dog.pk]))
        self.assertContains(response, 'Vaccination &amp; COI')
        self.assertContains(response, 'No appointments yet')

    def test_revert_pipeline_stage(self):
        self._pass_meet_greet()
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.EVALUATION)
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.post(reverse('operations:revert_pipeline', args=[self.dog.pk]))
        self.assertEqual(response.status_code, 302)
        self.dog.refresh_from_db()
        self.assertEqual(self.dog.pipeline_stage, ClientProfile.PipelineStage.MEET_GREET)

    def test_intake_creates_visible_meet_greet_visit(self):
        form = IntakeWizardForm(data={
            'owner_name': 'Visible Owner',
            'owner_email': 'visible-mg@example.com',
            'owner_phone': '4165550111',
            'dog_name': 'LuluVisible',
            'meet_greet_start': 'August 30, 2026 10 am',
        })
        self.assertTrue(form.is_valid(), form.errors)
        _, dog, visit = form.save()
        self.assertIsNotNone(visit)
        user = get_user_model().objects.create_user('david', 'd@example.com', 'pass')
        self.client.force_login(user)
        response = self.client.get(reverse('operations:dog_detail', args=[dog.pk]))
        self.assertContains(response, 'MEET &amp; GREET')
        self.assertContains(response, visit.schedule_display.split('–')[0].strip()[:6])