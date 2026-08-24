from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.forms.customers import CustomerOwnerForm
from operations.models import ClientProfile, Visit
from operations.services.contacts import is_valid_dog_name
from operations.services.datetime_parse import format_datetime_display, parse_datetime_text

_DATETIME_WIDGET = forms.TextInput(attrs={
    'placeholder': 'e.g. April 11, 2026 5 pm',
    'autocomplete': 'off',
    'spellcheck': 'false',
    'class': 'datetime-text-input',
})

_PHONE_WIDGET = forms.TextInput(attrs={
    'placeholder': 'Mobile number',
    'autocomplete': 'tel',
    'inputmode': 'tel',
})


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
    )
    meet_greet_end = forms.CharField(
        required=False,
        label='Meet & Greet end',
        widget=_DATETIME_WIDGET,
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
        dog_name = cleaned.get('dog_name')
        email = cleaned.get('owner_email')
        if dog_name and email and ClientProfile.objects.filter(
            owner_email__iexact=email,
            dog_name__iexact=dog_name,
        ).exists():
            self.add_error('dog_name', f'{dog_name} is already on file for this email.')

        start_text = (cleaned.get('meet_greet_start') or '').strip()
        end_text = (cleaned.get('meet_greet_end') or '').strip()
        if start_text or end_text:
            if not start_text or not end_text:
                self.add_error(
                    'meet_greet_end' if start_text else 'meet_greet_start',
                    'Enter both Meet & Greet start and end, or leave both blank.',
                )
                return cleaned
            try:
                scheduled_start = parse_datetime_text(start_text)
            except ValueError as exc:
                self.add_error('meet_greet_start', str(exc))
                return cleaned
            try:
                scheduled_end = parse_datetime_text(end_text, default=scheduled_start)
            except ValueError as exc:
                self.add_error('meet_greet_end', str(exc))
                return cleaned
            if scheduled_end <= scheduled_start:
                self.add_error('meet_greet_end', 'End must be after the start.')
                return cleaned
            cleaned['meet_greet_start_dt'] = scheduled_start
            cleaned['meet_greet_end_dt'] = scheduled_end
            probe = Visit(
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
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
            visit = Visit.objects.create(
                client=dog,
                scheduled_start=self.cleaned_data['meet_greet_start_dt'],
                scheduled_end=self.cleaned_data['meet_greet_end_dt'],
                notes='Meet & Greet — intake',
            )
        return owner, dog, visit
