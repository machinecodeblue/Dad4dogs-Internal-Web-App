from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.models import BusinessService, ClientProfile, Visit
from operations.services.context_tenant import get_active_workspace
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from operations.services.pipeline import MEET_GREET_SLUG

_DATETIME_WIDGET = forms.TextInput(attrs={
    'placeholder': 'e.g. August 30, 2026 10 am',
    'autocomplete': 'off',
    'spellcheck': 'false',
    'class': 'datetime-text-input',
})

MEET_GREET_MINUTES = 15


class MeetGreetScheduleForm(forms.Form):
    """One-off Meet & Greet booking — not VisitForm."""

    start_at = forms.CharField(
        label='Appointment date & start time',
        widget=_DATETIME_WIDGET,
        help_text='Duration is fixed at 15 minutes.',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Gate instructions, owner notes…',
        }),
    )
    send_confirmation_email = forms.BooleanField(
        label='Send booking confirmation email',
        required=False,
        initial=False,
    )

    def __init__(self, *args, dog: ClientProfile, **kwargs):
        super().__init__(*args, **kwargs)
        self.dog = dog
        if dog.owner_email:
            self.fields['send_confirmation_email'].label = (
                f'Send booking confirmation to {dog.owner_email}'
            )
        else:
            del self.fields['send_confirmation_email']

    def _resolve_service(self):
        workspace = get_active_workspace()
        return BusinessService.objects.filter(
            tenant=workspace,
            slug=MEET_GREET_SLUG,
            is_active=True,
        ).first()

    def clean(self):
        cleaned = super().clean()
        start_text = (cleaned.get('start_at') or '').strip()
        if not start_text:
            return cleaned

        if not self.dog.can_schedule_meet_greet():
            raise ValidationError(
                f'{self.dog.dog_name} cannot book Meet & Greet in '
                f'{self.dog.get_pipeline_stage_display()}.',
            )

        open_mg = self.dog.visits.filter(
            business_service__slug=MEET_GREET_SLUG,
            status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN],
        ).exists()
        if open_mg:
            raise ValidationError(
                f'{self.dog.dog_name} already has a Meet & Greet on the calendar. '
                f'Complete or cancel it before booking another.',
            )

        try:
            scheduled_start = parse_datetime_text(start_text)
        except ValueError as exc:
            self.add_error('start_at', str(exc))
            return cleaned

        scheduled_end = scheduled_start + timedelta(minutes=MEET_GREET_MINUTES)
        service = self._resolve_service()
        if service is None:
            raise ValidationError(
                f'Meet & Greet service (slug "{MEET_GREET_SLUG}") is missing. '
                f'Add it under Settings → Services.',
            )

        probe = Visit(
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            business_service=service,
        )
        probe.client_id = self.dog.pk
        capacity = check_visit_capacity(probe)
        if capacity['status'] == 'blocked':
            self.add_error(
                'start_at',
                f'Cannot schedule {format_datetime_display(scheduled_start)}: {capacity["message"]}',
            )
            return cleaned

        cleaned['scheduled_start'] = scheduled_start
        cleaned['scheduled_end'] = scheduled_end
        cleaned['business_service'] = service
        return cleaned

    @transaction.atomic
    def save(self) -> Visit:
        visit = Visit.objects.create(
            client=self.dog,
            scheduled_start=self.cleaned_data['scheduled_start'],
            scheduled_end=self.cleaned_data['scheduled_end'],
            notes=self.cleaned_data.get('notes') or '',
            business_service=self.cleaned_data['business_service'],
        )
        if self.dog.pipeline_stage == ClientProfile.PipelineStage.INQUIRY:
            self.dog.pipeline_stage = ClientProfile.PipelineStage.MEET_GREET
            self.dog.save(update_fields=['pipeline_stage', 'updated_at'])
        return visit
