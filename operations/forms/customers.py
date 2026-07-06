from django import forms
from django.core.exceptions import ValidationError

from operations.models import ClientProfile, CustomerOwner, VaccinationRecord


class CustomerOwnerForm(forms.ModelForm):
    class Meta:
        model = CustomerOwner
        fields = ['owner_name', 'owner_email', 'owner_phone']
        widgets = {
            'owner_name': forms.TextInput(attrs={
                'placeholder': 'Owner full name',
                'autocomplete': 'name',
            }),
            'owner_email': forms.EmailInput(attrs={
                'placeholder': 'owner@email.com',
                'autocomplete': 'email',
                'inputmode': 'email',
            }),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': 'Optional',
                'autocomplete': 'tel',
                'inputmode': 'tel',
            }),
        }


class DogProfileForm(forms.ModelForm):
    """Dog only — pipeline and notes. Owner comes from the customer record."""

    class Meta:
        model = ClientProfile
        fields = ['dog_name', 'pipeline_stage', 'notes']
        widgets = {
            'dog_name': forms.TextInput(attrs={
                'placeholder': 'e.g. Kobe',
                'autocomplete': 'off',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Breed, temperament, special instructions…',
            }),
        }

    def __init__(self, *args, customer_owner: CustomerOwner | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer_owner = customer_owner
        if self.instance.pk and not self.customer_owner:
            self.customer_owner = CustomerOwner.ensure_for_client(self.instance)

    def clean_dog_name(self):
        dog_name = self.cleaned_data['dog_name'].strip()
        if not dog_name:
            raise ValidationError('Dog name is required.')
        if self.customer_owner:
            owner_first = self.customer_owner.owner_name.split()[0].lower()
            if dog_name.lower() == owner_first:
                raise ValidationError(
                    'Dog name cannot be the same as the owner\'s first name.',
                )
        if dog_name.upper() in ('TBD', 'UNKNOWN'):
            raise ValidationError('Enter the dog\'s real name.')
        return dog_name

    def clean(self):
        cleaned = super().clean()
        dog_name = cleaned.get('dog_name')
        if dog_name and self.customer_owner:
            qs = ClientProfile.objects.filter(
                owner_email__iexact=self.customer_owner.owner_email,
                dog_name__iexact=dog_name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(f'{dog_name} is already on file for this customer.')
        return cleaned

    def save(self, commit=True):
        dog = super().save(commit=False)
        if self.customer_owner:
            dog.owner_name = self.customer_owner.owner_name
            dog.owner_email = self.customer_owner.owner_email
            dog.owner_phone = self.customer_owner.owner_phone
        if commit:
            dog.save()
        return dog


class VaccinationRecordForm(forms.ModelForm):
    class Meta:
        model = VaccinationRecord
        fields = [
            'client',
            'papers_received',
            'received_at',
            'expires_at',
            'vet_clinic',
            'vaccination_details',
            'notes',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'dog-select'}),
            'received_at': forms.DateInput(attrs={'type': 'date'}),
            'expires_at': forms.DateInput(attrs={'type': 'date'}),
            'vet_clinic': forms.TextInput(attrs={'placeholder': 'Vet hospital name'}),
            'vaccination_details': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Rabies, kennel cough, expiry dates…',
            }),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }

    def __init__(self, *args, fixed_client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].label = 'Dog (who these papers belong to)'
        self.fields['client'].queryset = ClientProfile.objects.all()
        if fixed_client:
            self.fields['client'].initial = fixed_client
            self.fields['client'].widget = forms.HiddenInput()