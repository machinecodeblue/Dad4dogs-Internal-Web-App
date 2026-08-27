from django import forms

from operations.models import BusinessProfile, CapacitySettings


class BusinessProfileForm(forms.ModelForm):
    """Edits BusinessProfile plus CapacitySettings on one settings screen."""

    standard_capacity = forms.IntegerField(
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'min': 1,
            'max': 50,
            'inputmode': 'numeric',
        }),
    )
    insurance_ceiling = forms.IntegerField(
        min_value=1,
        max_value=50,
        widget=forms.NumberInput(attrs={
            'min': 1,
            'max': 50,
            'inputmode': 'numeric',
        }),
    )

    class Meta:
        model = BusinessProfile
        fields = [
            'business_name',
            'business_email',
            'address',
            'hours_of_operation',
            'main_phone',
            'secondary_phone',
            'emergency_phone',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={
                'placeholder': 'David Lundquist (Dad 4 Dogs)',
                'autocomplete': 'organization',
            }),
            'business_email': forms.EmailInput(attrs={
                'placeholder': 'david@machinecodeblue.com',
                'autocomplete': 'email',
                'inputmode': 'email',
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Street, city, province, postal code',
                'autocomplete': 'street-address',
            }),
            'hours_of_operation': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'e.g. Mon–Fri 7:00 AM – 7:00 PM, weekends by appointment',
            }),
            'main_phone': forms.TextInput(attrs={
                'placeholder': 'Main business line',
                'autocomplete': 'tel',
                'inputmode': 'tel',
            }),
            'secondary_phone': forms.TextInput(attrs={
                'placeholder': 'Secondary line (optional)',
                'autocomplete': 'tel',
                'inputmode': 'tel',
            }),
            'emergency_phone': forms.TextInput(attrs={
                'placeholder': 'Emergency contact number',
                'autocomplete': 'tel',
                'inputmode': 'tel',
            }),
        }

    def __init__(self, *args, capacity_settings: CapacitySettings | None = None, **kwargs):
        self.capacity_settings = capacity_settings
        super().__init__(*args, **kwargs)
        if capacity_settings is not None:
            self.fields['standard_capacity'].initial = capacity_settings.standard_capacity
            self.fields['insurance_ceiling'].initial = capacity_settings.insurance_ceiling

    def clean(self):
        cleaned = super().clean()
        standard = cleaned.get('standard_capacity')
        ceiling = cleaned.get('insurance_ceiling')
        if standard is not None and ceiling is not None and ceiling < standard:
            self.add_error(
                'insurance_ceiling',
                'Insurance maximum must be at least the standard daily capacity.',
            )
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit and self.capacity_settings is not None:
            self.capacity_settings.standard_capacity = self.cleaned_data['standard_capacity']
            self.capacity_settings.insurance_ceiling = self.cleaned_data['insurance_ceiling']
            self.capacity_settings.full_clean()
            self.capacity_settings.save()
        return profile
