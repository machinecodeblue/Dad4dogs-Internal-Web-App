from django import forms

from operations.models import Visit


class EvaluationOutcomeForm(forms.Form):
    evaluation_notes = forms.CharField(
        label='Evaluation notes',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'How did the dog do in the pack? Temperament, play style, any concerns…',
        }),
        help_text='Required. Describe the stay and why you chose this outcome.',
    )
    evaluation_outcome = forms.ChoiceField(
        label='Outcome',
        choices=Visit.EvaluationOutcome.choices,
        widget=forms.RadioSelect,
    )


class MeetGreetOutcomeForm(forms.Form):
    meet_greet_notes = forms.CharField(
        label='Meet & Greet notes',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Suitability, owner fit, any concerns…',
        }),
        help_text='Required. Pass only if you want this dog on the Evaluation track.',
    )
    meet_greet_outcome = forms.ChoiceField(
        label='Outcome',
        choices=Visit.MeetGreetOutcome.choices,
        widget=forms.RadioSelect,
    )
