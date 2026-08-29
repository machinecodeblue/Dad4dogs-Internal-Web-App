from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.forms.customers import CustomerOwnerForm, _PHONE_WIDGET
from operations.models import BusinessService, ClientProfile, Visit
from operations.services.contacts import is_valid_dog_name
from operations.services.context_tenant import get_active_workspace
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text

_DATETIME_WIDGET = forms.TextInput(attrs={
    'placeholder': 'e.g. April 11, 2026 5 pm',
    'autocomplete': 'off',
    'spellcheck': 'false',
    'class': 'datetime-text-input',
})

MEET_GREET_SLUG = 'meet_greet'
MEET_GREET_DEFAULT_MINUTES = 15


def _resolve_meet_greet_service():
    workspace = get_active_workspace()
    return BusinessService.objects.filter(
        tenant=workspace,
        slug=MEET_GREET_SLUG,
        is_active=True,
    ).first()


class IntakeWizardForm(CustomerOwnerForm):
    """One POST: owner + first dog + optional Meet & Greet visit."""

    dog_name = forms.CharField(
        label='Dog name',
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Kobe',
            'autocomplete': 'off',
        }),
    )
    vet_clinic_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'placeholder': 'e.g. Grey Street Animal Hospital',
    }))
    vet_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'placeholder': 'Primary veterinarian',
    }))
    vet_clinic_phone = forms.CharField(required=False, widget=_PHONE_WIDGET)
    emergency_vet_clinic = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'placeholder': 'Preferred 24-hour emergency hospital',
    }))
    emergency_vet_phone = forms.CharField(required=False, widget=_PHONE_WIDGET)
    vet_care_authorization = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'e.g. Approve up to $500 lifesaving triage before contacting me',
        }),
    )
    dog_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Breed, temperament, special handling…',
        }),
    )
    meet_greet_start = forms.CharField(
        required=False,
        label='Meet & Greet start',
        widget=_DATETIME_WIDGET,
        help_text='Optional. Leave end blank to default to 15 minutes after start.',
    )
    meet_greet_end = forms.CharField(
        required=False,
        label='Meet & Greet end',
        widget=_DATETIME_WIDGET,
        help_text='Optional. Defaults to 15 minutes after start when blank.',
    )

    def clean_dog_name(self):
        dog_name = self.cleaned_data['dog_name'].strip()
        owner_name = (self.cleaned_data.get('owner_name') or self.data.get('owner_name') or '').strip()
        if not is_valid_dog_name(dog_name, owner_name):
            raise ValidationError(
                "Enter the dog's real name — not TBD, and not the owner's first name.",
            )
        return dog_name

    def clean(self):
        cleaned = super().clean()
        dog_name = (cleaned.get('dog_name') or '').strip()
        if dog_name:
            cleaned['dog_name'] = dog_name
        email = cleaned.get('owner_email')
        if dog_name and email and ClientProfile.objects.filter(
            owner_email__iexact=email,
            dog_name__iexact=dog_name,
        ).exists():
            self.add_error('dog_name', f'{dog_name} is already on file for this email.')

        start_text = (cleaned.get('meet_greet_start') or '').strip()
        end_text = (cleaned.get('meet_greet_end') or '').strip()
        if not start_text and not end_text:
            return cleaned

        if not start_text and end_text:
            self.add_error('meet_greet_start', 'Enter a Meet & Greet start, or leave both times blank.')
            return cleaned

        try:
            scheduled_start = parse_datetime_text(start_text)
        except ValueError as exc:
            self.add_error('meet_greet_start', str(exc))
            return cleaned

        if end_text:
            try:
                scheduled_end = parse_datetime_text(end_text, default=scheduled_start)
            except ValueError as exc:
                self.add_error('meet_greet_end', str(exc))
                return cleaned
        else:
            scheduled_end = scheduled_start + timedelta(minutes=MEET_GREET_DEFAULT_MINUTES)

        if scheduled_end <= scheduled_start:
            self.add_error('meet_greet_end', 'End must be after the start.')
            return cleaned

        meet_service = _resolve_meet_greet_service()
        if meet_service is None:
            self.add_error(
                None,
                'Meet & Greet service definition is missing. '
                'Add an active Meet & Greet offering under Settings → Services '
                f'(slug "{MEET_GREET_SLUG}").',
            )
            return cleaned

        cleaned['meet_greet_start_dt'] = scheduled_start
        cleaned['meet_greet_end_dt'] = scheduled_end
        cleaned['meet_greet_service'] = meet_service

        probe = Visit(
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            business_service=meet_service,
        )
        probe.client_id = 0
        capacity = check_visit_capacity(probe)
        if capacity['status'] == 'blocked':
            self.add_error(
                'meet_greet_start',
                f'Cannot schedule {format_datetime_display(scheduled_start)}: {capacity["message"]}',
            )
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        owner = super().save(commit=commit)
        if not commit:
            return owner, None, None
        has_meet = 'meet_greet_start_dt' in self.cleaned_data
        stage = (
            ClientProfile.PipelineStage.MEET_GREET
            if has_meet
            else ClientProfile.PipelineStage.INQUIRY
        )
        dog = ClientProfile(
            dog_name=self.cleaned_data['dog_name'],
            owner_name=owner.owner_name,
            owner_email=owner.owner_email,
            owner_phone=owner.owner_phone,
            pipeline_stage=stage,
            vet_clinic_name=self.cleaned_data.get('vet_clinic_name') or '',
            vet_name=self.cleaned_data.get('vet_name') or '',
            vet_clinic_phone=self.cleaned_data.get('vet_clinic_phone') or '',
            emergency_vet_clinic=self.cleaned_data.get('emergency_vet_clinic') or '',
            emergency_vet_phone=self.cleaned_data.get('emergency_vet_phone') or '',
            vet_care_authorization=self.cleaned_data.get('vet_care_authorization') or '',
            notes=self.cleaned_data.get('dog_notes') or '',
        )
        dog.save()
        dog.ensure_feed_credentials()
        visit = None
        if has_meet:
            meet_service = self.cleaned_data['meet_greet_service']
            visit = Visit.objects.create(
                client=dog,
                scheduled_start=self.cleaned_data['meet_greet_start_dt'],
                scheduled_end=self.cleaned_data['meet_greet_end_dt'],
                notes='Meet & Greet — intake',
                business_service=meet_service,
            )
        return owner, dog, visit
