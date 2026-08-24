from django import forms
from django.core.exceptions import ValidationError

from operations.models import ClientProfile, CustomerOwner, VaccinationRecord
from operations.services.addresses import (
    CANADIAN_PROVINCES,
    normalize_postal_code,
    normalize_province,
    parse_legacy_address,
)
from operations.services.contacts import is_valid_dog_name, normalize_email
from operations.services.phones import validate_phone

_PHONE_WIDGET = forms.TextInput(attrs={
    'placeholder': '416-555-0100',
    'autocomplete': 'tel',
    'inputmode': 'tel',
})


class _ProvinceChoiceField(forms.ChoiceField):
    """Select of province codes; empty stays '', aliases like 'Ontario' become 'ON'."""

    def valid_value(self, value):
        if value in self.empty_values:
            return True
        try:
            return bool(normalize_province(str(value)))
        except ValueError:
            return False

    def clean(self, value):
        value = super().clean(value)
        if value in self.empty_values or value is None:
            return ''
        try:
            return normalize_province(str(value))
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class NanpPhoneFormMixin:
    """Normalize owner / emergency / vet phones to 10-digit NANP."""

    def _cleaned_phone(self, field: str, *, required: bool = False):
        message = 'Primary mobile phone is required.' if required else None
        try:
            return validate_phone(
                self.cleaned_data.get(field),
                required=required,
                **({'required_message': message} if message else {}),
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def clean_owner_phone(self):
        return self._cleaned_phone('owner_phone', required=True)

    def clean_emergency_contact_phone(self):
        return self._cleaned_phone('emergency_contact_phone')

    def clean_vet_clinic_phone(self):
        return self._cleaned_phone('vet_clinic_phone')

    def clean_emergency_vet_phone(self):
        return self._cleaned_phone('emergency_vet_phone')


class CustomerOwnerForm(NanpPhoneFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerOwner
        fields = [
            'owner_name',
            'owner_salutation',
            'owner_email',
            'owner_phone',
            'address_street',
            'address_unit',
            'address_city',
            'address_province',
            'address_postal_code',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relationship',
            'authorized_pickup_names',
        ]
        widgets = {
            'owner_name': forms.TextInput(attrs={
                'placeholder': 'Owner full name',
                'autocomplete': 'name',
            }),
            'owner_salutation': forms.TextInput(attrs={
                'placeholder': 'Optional — Ms., they/them, etc.',
            }),
            'owner_email': forms.EmailInput(attrs={
                'placeholder': 'owner@email.com',
                'autocomplete': 'email',
                'inputmode': 'email',
            }),
            'owner_phone': _PHONE_WIDGET,
            'address_street': forms.TextInput(attrs={
                'placeholder': '191 Grey Street',
                'autocomplete': 'address-line1',
            }),
            'address_unit': forms.TextInput(attrs={
                'placeholder': 'Optional — 2B',
                'autocomplete': 'address-line2',
            }),
            'address_city': forms.TextInput(attrs={
                'placeholder': 'London',
                'autocomplete': 'address-level2',
            }),
            'address_province': forms.Select(attrs={
                'autocomplete': 'address-level1',
            }),
            'address_postal_code': forms.TextInput(attrs={
                'placeholder': 'N6B 1G2',
                'autocomplete': 'postal-code',
                'inputmode': 'text',
                'autocapitalize': 'characters',
            }),
            'emergency_contact_name': forms.TextInput(attrs={
                'placeholder': 'Trusted friend, neighbor, or family member',
            }),
            'emergency_contact_phone': _PHONE_WIDGET,
            'emergency_contact_relationship': forms.TextInput(attrs={
                'placeholder': 'e.g. Neighbor with house key',
            }),
            'authorized_pickup_names': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'One authorized pickup name per line',
            }),
        }
        labels = {
            'address_street': 'Street',
            'address_unit': 'Unit / Apt',
            'address_city': 'City',
            'address_province': 'Province',
            'address_postal_code': 'Postal code',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['address_province'] = _ProvinceChoiceField(
            required=False,
            choices=[('', 'Province')] + list(CANADIAN_PROVINCES),
            widget=forms.Select(attrs={'autocomplete': 'address-level1'}),
            label='Province',
        )
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.home_address:
            parsed = parse_legacy_address(instance.home_address)
            legacy_to_field = {
                'address_street': parsed['street'],
                'address_unit': parsed['unit'],
                'address_city': parsed['city'],
                'address_province': parsed['province'],
                'address_postal_code': parsed['postal'],
            }
            for field, value in legacy_to_field.items():
                if value and not getattr(instance, field) and not self.initial.get(field):
                    self.initial[field] = value

    def clean_owner_email(self):
        email = normalize_email(self.cleaned_data.get('owner_email') or '')
        if not email:
            raise ValidationError('Email is required.')
        qs = CustomerOwner.objects.filter(owner_email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A customer with this email is already on file.')
        return email

    def clean_address_postal_code(self):
        raw = (self.cleaned_data.get('address_postal_code') or '').strip()
        if not raw:
            return ''
        try:
            return normalize_postal_code(raw)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def clean_address_province(self):
        raw = (self.cleaned_data.get('address_province') or '').strip()
        if not raw:
            return ''
        try:
            return normalize_province(raw)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def clean_authorized_pickup_names(self):
        raw = self.cleaned_data.get('authorized_pickup_names') or ''
        names = [line.strip() for line in raw.splitlines() if line.strip()]
        return '\n'.join(names)

    def clean(self):
        cleaned = super().clean()
        street = (cleaned.get('address_street') or '').strip()
        unit = (cleaned.get('address_unit') or '').strip()
        city = (cleaned.get('address_city') or '').strip()
        province = cleaned.get('address_province') or ''
        postal = (cleaned.get('address_postal_code') or '').strip()
        cleaned['address_street'] = street
        cleaned['address_unit'] = unit
        cleaned['address_city'] = city
        cleaned['address_province'] = province
        cleaned['address_postal_code'] = postal
        if any((street, unit, city, province, postal)):
            if not street:
                self.add_error('address_street', 'Enter the street, or clear the other address fields.')
            if not city:
                self.add_error('address_city', 'Enter the city, or clear the other address fields.')
            if not province:
                self.add_error('address_province', 'Choose a province, or clear the other address fields.')
            if not postal:
                self.add_error(
                    'address_postal_code',
                    'Enter the postal code, or clear the other address fields.',
                )
        return cleaned


class DogProfileForm(NanpPhoneFormMixin, forms.ModelForm):
    """Dog only — pipeline, vet contacts, notes. Owner comes from the customer record."""

    class Meta:
        model = ClientProfile
        fields = [
            'dog_name',
            'pipeline_stage',
            'vet_clinic_name',
            'vet_name',
            'vet_clinic_phone',
            'emergency_vet_clinic',
            'emergency_vet_phone',
            'vet_care_authorization',
            'notes',
        ]
        widgets = {
            'dog_name': forms.TextInput(attrs={
                'placeholder': 'e.g. Kobe',
                'autocomplete': 'off',
            }),
            'vet_clinic_name': forms.TextInput(attrs={
                'placeholder': 'e.g. Grey Street Animal Hospital',
            }),
            'vet_name': forms.TextInput(attrs={
                'placeholder': 'Primary veterinarian',
            }),
            'vet_clinic_phone': _PHONE_WIDGET,
            'emergency_vet_clinic': forms.TextInput(attrs={
                'placeholder': 'Preferred 24-hour emergency hospital',
            }),
            'emergency_vet_phone': _PHONE_WIDGET,
            'vet_care_authorization': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'e.g. Approve up to $500 lifesaving triage before contacting me',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Breed, temperament, special handling instructions…',
            }),
        }

    def __init__(self, *args, customer_owner: CustomerOwner | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer_owner = customer_owner
        if self.instance.pk and not self.customer_owner:
            self.customer_owner = CustomerOwner.for_client(self.instance)

    def clean_dog_name(self):
        dog_name = self.cleaned_data['dog_name'].strip()
        if not dog_name:
            raise ValidationError('Dog name is required.')
        owner_name = self.customer_owner.owner_name if self.customer_owner else ''
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
        if dog_name and self.customer_owner:
            qs = ClientProfile.objects.filter(
                owner_email__iexact=self.customer_owner.owner_email,
                dog_name__iexact=dog_name,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'dog_name',
                    f'{dog_name} is already on file for this customer.',
                )
        return cleaned

    def save(self, commit=True):
        dog = super().save(commit=False)
        owner = self.customer_owner
        if owner is None and dog.pk:
            owner = CustomerOwner.ensure_for_client(dog)
            self.customer_owner = owner
        if owner:
            dog.owner_name = owner.owner_name
            dog.owner_email = owner.owner_email
            dog.owner_phone = owner.owner_phone
        dog.ensure_feed_credentials(save=False)
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
            'papers_received': forms.CheckboxInput(),
            'vet_clinic': forms.TextInput(attrs={'placeholder': 'Vet hospital name'}),
            'vaccination_details': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Rabies, kennel cough, expiry dates…',
            }),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes'}),
        }
        labels = {
            'received_at': 'Date papers received',
            'expires_at': 'Vaccination expiry date',
        }

    def __init__(self, *args, fixed_client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_client = fixed_client
        self.fields['client'].label = 'Dog (who these papers belong to)'
        self.fields['client'].queryset = ClientProfile.objects.all()
        self.fields['papers_received'].required = False
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.initial.setdefault('papers_received', True)
        if fixed_client:
            self.instance.client = fixed_client
            self.fields['client'].initial = fixed_client
            self.fields['client'].required = False
            self.fields['client'].widget = forms.HiddenInput()

    def clean_client(self):
        if self.fixed_client:
            return self.fixed_client
        return self.cleaned_data.get('client')

    def clean(self):
        cleaned = super().clean()
        if self.fixed_client:
            cleaned['client'] = self.fixed_client
        received = cleaned.get('received_at')
        expires = cleaned.get('expires_at')
        if received and expires and expires < received:
            self.add_error(
                'expires_at',
                'Expiry date must be on or after the date papers were received.',
            )
        return cleaned

    def save(self, commit=True):
        record = super().save(commit=False)
        if self.fixed_client:
            record.client = self.fixed_client
        if commit:
            record.save()
        return record