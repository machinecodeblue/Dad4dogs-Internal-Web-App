from django import forms

from operations.models import BusinessProfile


class BusinessProfileForm(forms.ModelForm):
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