from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.models import BusinessService, ClientProfile, Visit
from operations.services.context_tenant import get_active_workspace
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text
from operations.services.pipeline import INITIAL_EVALUATION_SLUG

_DATETIME_WIDGET = forms.TextInput(attrs={
    'placeholder': 'e.g. September 5, 2026 10 am',
    'autocomplete': 'off',
    'spellcheck': 'false',
    'class': 'datetime-text-input',
})

EVALUATION_HOURS = 4


class EvaluationScheduleForm(forms.Form):
    """One-off Initial Evaluation booking — not VisitForm."""

    start_at = forms.CharField(
        label='Appointment date & start time',
        widget=_DATETIME_WIDGET,
        help_text='Duration is fixed at 4 hours.',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Pack focus, owner notes…',
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
            slug=INITIAL_EVALUATION_SLUG,
            is_active=True,
        ).first()

    def clean(self):
        cleaned = super().clean()
        start_text = (cleaned.get('start_at') or '').strip()
        if not start_text:
            return cleaned

        for message in self.dog.evaluation_stay_blockers():
            raise ValidationError(message)

        open_eval = self.dog.visits.filter(
            business_service__slug=INITIAL_EVALUATION_SLUG,
            status__in=[Visit.Status.SCHEDULED, Visit.Status.CHECKED_IN],
        ).exists()
        if open_eval:
            raise ValidationError(
                f'{self.dog.dog_name} already has an Initial Evaluation on the calendar.',
            )

        completed_evals = list(
            self.dog.visits.filter(
                business_service__slug=INITIAL_EVALUATION_SLUG,
                status=Visit.Status.COMPLETED,
            ).order_by('-actual_departure', '-scheduled_end')
        )
        if completed_evals:
            latest = completed_evals[0]
            if latest.evaluation_outcome != Visit.EvaluationOutcome.FURTHER:
                raise ValidationError(
                    f'{self.dog.dog_name} already has an Initial Evaluation. '
                    f'Book another only after outcome “Recommend further evaluation”.',
                )

        try:
            scheduled_start = parse_datetime_text(start_text)
        except ValueError as exc:
            self.add_error('start_at', str(exc))
            return cleaned

        scheduled_end = scheduled_start + timedelta(hours=EVALUATION_HOURS)
        service = self._resolve_service()
        if service is None:
            raise ValidationError(
                f'Initial Evaluation service (slug "{INITIAL_EVALUATION_SLUG}") is missing.',
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
        return Visit.objects.create(
            client=self.dog,
            scheduled_start=self.cleaned_data['scheduled_start'],
            scheduled_end=self.cleaned_data['scheduled_end'],
            notes=self.cleaned_data.get('notes') or '',
            business_service=self.cleaned_data['business_service'],
        )
