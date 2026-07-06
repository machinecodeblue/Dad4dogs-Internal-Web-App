from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from operations.capacity import check_visit_capacity
from operations.models import ClientProfile, Visit, VisitSeries
from operations.services.datetime_parse import format_datetime_display, format_datetime_input, parse_datetime_text
from operations.services.visit_repeat import (
    END_AFTER,
    FREQUENCY_CHOICES,
    FREQUENCY_NONE,
    generate_repeat_occurrences,
    parse_repeat_ends,
)


class VisitForm(forms.Form):
    """Create or edit a visit using free-text start/end date-time."""

    start_at = forms.CharField(
        label='Start',
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. April 11, 2026 5 pm',
            'autocomplete': 'off',
            'spellcheck': 'false',
            'class': 'datetime-text-input',
        }),
    )
    end_at = forms.CharField(
        label='End',
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. April 28, 2026 5 pm',
            'autocomplete': 'off',
            'spellcheck': 'false',
            'class': 'datetime-text-input',
        }),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Optional notes',
        }),
    )
    repeat_frequency = forms.ChoiceField(
        label='Repeat',
        choices=FREQUENCY_CHOICES,
        initial=FREQUENCY_NONE,
        required=False,
    )
    repeat_interval = forms.IntegerField(
        label='Every',
        min_value=1,
        max_value=30,
        initial=1,
        required=False,
        widget=forms.NumberInput(attrs={'style': 'width:4.5rem', 'min': 1}),
    )
    repeat_ends = forms.CharField(
        label='Ends',
        initial='5',
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '5 or April 15, 2026',
            'autocomplete': 'off',
            'class': 'datetime-text-input',
        }),
        help_text='Number of visits, or last date — type or dictate either one.',
    )
    send_confirmation_email = forms.BooleanField(
        label='Send booking confirmation email',
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'confirm-email-checkbox'}),
    )

    def __init__(
        self,
        *args,
        client: ClientProfile | None = None,
        instance: Visit | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.client = client
        self.instance = instance
        if instance:
            self.fields['start_at'].initial = format_datetime_input(instance.scheduled_start)
            self.fields['end_at'].initial = format_datetime_input(instance.scheduled_end)
            self.fields['notes'].initial = instance.notes
            self.client = instance.client
            for name in (
                'repeat_frequency',
                'repeat_interval',
                'repeat_ends',
                'send_confirmation_email',
            ):
                del self.fields[name]
        elif self.client and self.client.owner_email:
            self.fields['send_confirmation_email'].label = (
                f'Send booking confirmation to {self.client.owner_email}'
            )
        else:
            del self.fields['send_confirmation_email']

    def clean(self):
        cleaned = super().clean()
        start_text = cleaned.get('start_at', '').strip()
        end_text = cleaned.get('end_at', '').strip()
        if not start_text or not end_text:
            return cleaned

        try:
            scheduled_start = parse_datetime_text(start_text)
        except ValueError as exc:
            self.add_error('start_at', str(exc))
            return cleaned

        try:
            scheduled_end = parse_datetime_text(end_text, default=scheduled_start)
        except ValueError as exc:
            self.add_error('end_at', str(exc))
            return cleaned

        if scheduled_end <= scheduled_start:
            self.add_error('end_at', 'End must be after the start.')

        cleaned['scheduled_start'] = scheduled_start
        cleaned['scheduled_end'] = scheduled_end

        if not self.instance:
            frequency = cleaned.get('repeat_frequency') or FREQUENCY_NONE
            if frequency != FREQUENCY_NONE:
                ends_text = (cleaned.get('repeat_ends') or '').strip()
                try:
                    end_type, count, until_dt = parse_repeat_ends(ends_text, scheduled_start)
                    cleaned['repeat_end_type'] = end_type
                    cleaned['repeat_count'] = count
                    cleaned['repeat_until_dt'] = until_dt
                except ValueError as exc:
                    self.add_error('repeat_ends', str(exc))

        return cleaned

    def _occurrences(self) -> list[tuple]:
        if self.instance:
            return [(
                self.cleaned_data['scheduled_start'],
                self.cleaned_data['scheduled_end'],
            )]
        frequency = self.cleaned_data.get('repeat_frequency') or FREQUENCY_NONE
        end_type = self.cleaned_data.get('repeat_end_type') or END_AFTER
        return generate_repeat_occurrences(
            self.cleaned_data['scheduled_start'],
            self.cleaned_data['scheduled_end'],
            frequency=frequency,
            interval=self.cleaned_data.get('repeat_interval') or 1,
            end_type=end_type,
            count=self.cleaned_data.get('repeat_count') or 1,
            until=self.cleaned_data.get('repeat_until_dt'),
        )

    def save(self) -> Visit:
        created = self.save_all()
        return created[0]

    @transaction.atomic
    def save_all(self) -> list[Visit]:
        if not self.client:
            raise ValidationError('Dog is required to schedule a visit.')
        notes = self.cleaned_data.get('notes', '')
        occurrences = self._occurrences()
        created: list[Visit] = []
        series = None

        if not self.instance and len(occurrences) > 1:
            frequency = self.cleaned_data.get('repeat_frequency') or FREQUENCY_NONE
            end_type = self.cleaned_data.get('repeat_end_type') or END_AFTER
            series = VisitSeries.objects.create(
                client=self.client,
                frequency=frequency,
                interval=self.cleaned_data.get('repeat_interval') or 1,
                end_type=end_type,
                total_occurrences=len(occurrences),
                until=self.cleaned_data.get('repeat_until_dt'),
                anchor_start=occurrences[0][0],
                anchor_end=occurrences[0][1],
                notes=notes,
            )

        for index, (occ_start, occ_end) in enumerate(occurrences, start=1):
            if self.instance and len(created) == 0:
                visit = self.instance
                visit.scheduled_start = occ_start
                visit.scheduled_end = occ_end
                visit.notes = notes
            else:
                visit = Visit(
                    client=self.client,
                    scheduled_start=occ_start,
                    scheduled_end=occ_end,
                    notes=notes,
                    series=series,
                    series_position=index if series else None,
                )
            capacity = check_visit_capacity(visit)
            if capacity['status'] == 'blocked':
                raise ValidationError(
                    f'Cannot schedule {format_datetime_display(occ_start)}: {capacity["message"]}',
                )
            visit.save()
            created.append(visit)

        return created


# Backwards-compatible alias
VisitScheduleForm = VisitForm


class TimelineMomentForm(forms.Form):
    """Capture or attach media for one or more checked-in visits."""

    visit_ids = forms.ModelMultipleChoiceField(
        queryset=Visit.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'timeline-visit-checkboxes'}),
        required=True,
        label='Also log for',
    )
    photo_camera = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'accept': 'image/*',
            'capture': 'environment',
            'class': 'timeline-photo-camera-input',
        }),
    )
    photo_gallery = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'accept': 'image/*',
            'class': 'timeline-photo-gallery-input',
        }),
    )
    video = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'accept': 'video/*',
            'class': 'timeline-video-input',
        }),
    )
    caption_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'Quick note or voice-to-text…',
            'class': 'timeline-caption-input',
        }),
    )
    latitude = forms.CharField(required=False, widget=forms.HiddenInput())
    longitude = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, eligible_visits=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = eligible_visits if eligible_visits is not None else Visit.objects.none()
        self.fields['visit_ids'].queryset = queryset
        self.fields['visit_ids'].label_from_instance = lambda visit: visit.client.dog_name

    def clean(self):
        cleaned = super().clean()
        photo = cleaned.get('photo_camera') or cleaned.get('photo_gallery')
        video = cleaned.get('video')
        media_count = sum(bool(x) for x in (photo, video))
        if media_count > 1:
            raise ValidationError('Submit one photo or one video.')
        if media_count == 0:
            raise ValidationError('Capture or choose a photo, or choose a video from your gallery.')
        cleaned['uploaded_file'] = photo or video
        cleaned['media_kind'] = 'photo' if photo else 'video'
        return cleaned


class TimelineForwardForm(forms.Form):
    visit_ids = forms.ModelMultipleChoiceField(
        queryset=Visit.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label='Share with',
    )

    def __init__(self, *args, eligible_visits=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = eligible_visits if eligible_visits is not None else Visit.objects.none()
        self.fields['visit_ids'].queryset = queryset
        self.fields['visit_ids'].label_from_instance = lambda visit: visit.client.dog_name