from django import forms

from operations.models import BusinessService, ServiceBehaviorRule


class BusinessServiceForm(forms.ModelForm):
    class Meta:
        model = BusinessService
        fields = [
            'name',
            'slug',
            'summary',
            'description',
            'staff_notes',
            'target_category',
            'rate_type',
            'base_rate',
            'is_active',
            'capacity_exempt',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Standard Overnight Stay'}),
            'slug': forms.TextInput(attrs={'placeholder': 'overnight_stay'}),
            'summary': forms.TextInput(attrs={
                'placeholder': 'Short list blurb (optional)',
                'maxlength': 240,
            }),
            'description': forms.Textarea(attrs={
                'rows': 6,
                'placeholder': (
                    'Full customer-facing plan: what is included, drop-off/pick-up '
                    'expectations, and boundaries. Plain text.'
                ),
            }),
            'staff_notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Internal only — never shown to customers',
            }),
            'base_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }


class ServiceBehaviorRuleForm(forms.ModelForm):
    class Meta:
        model = ServiceBehaviorRule
        fields = [
            'trigger_type',
            'threshold_value',
            'modified_rate',
        ]
        widgets = {
            'threshold_value': forms.NumberInput(attrs={'min': 0}),
            'modified_rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
