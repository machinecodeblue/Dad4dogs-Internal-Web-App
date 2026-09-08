"""Public booking manage page forms (client confirm / reschedule / cancel)."""

from django import forms

from operations.services.datetime_parse import format_datetime_input, parse_datetime_text


class BookingRescheduleForm(forms.Form):
    start_text = forms.CharField(
        label='Start',
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'inputmode': 'text',
            'placeholder': 'e.g. September 11 2026 2 p.m.',
        }),
    )
    end_text = forms.CharField(
        label='End',
        widget=forms.TextInput(attrs={
            'autocomplete': 'off',
            'inputmode': 'text',
            'placeholder': 'e.g. September 11 2026 6 p.m.',
        }),
    )

    def __init__(self, *args, visit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.visit = visit
        if visit is not None and not self.is_bound:
            self.fields['start_text'].initial = format_datetime_input(visit.scheduled_start)
            self.fields['end_text'].initial = format_datetime_input(visit.scheduled_end)

    def clean(self):
        cleaned = super().clean()
        start_text = cleaned.get('start_text')
        end_text = cleaned.get('end_text')
        if not start_text or not end_text:
            return cleaned
        try:
            start = parse_datetime_text(start_text)
        except ValueError as exc:
            self.add_error('start_text', str(exc))
            return cleaned
        try:
            end = parse_datetime_text(end_text, default=start)
        except ValueError as exc:
            self.add_error('end_text', str(exc))
            return cleaned
        if end <= start:
            self.add_error('end_text', 'End must be after start.')
            return cleaned
        cleaned['scheduled_start'] = start
        cleaned['scheduled_end'] = end
        return cleaned
