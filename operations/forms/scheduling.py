from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from operations.capacity import check_visit_capacity, overlapping_dog_visit
from operations.models import BusinessService, ClientProfile, Visit, VisitSeries
from operations.services.context_tenant import get_active_workspace
from operations.services.datetime_parse import format_datetime_display, format_datetime_input, parse_datetime_text
from operations.services.visit_repeat import (
    END_AFTER,
    END_ON,
    FREQUENCY_CHOICES,
    FREQUENCY_NONE,
    MAX_OCCURRENCES,
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
    business_service = forms.ModelChoiceField(
        label='Service',
        queryset=BusinessService.objects.none(),
        required=True,
        empty_label='Select a service…',
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
        workspace = get_active_workspace()
        service_field = self.fields['business_service']
        service_field.queryset = (
            BusinessService.objects.filter(tenant=workspace, is_active=True)
            .order_by('target_category', 'name')
        )
        service_field.label_from_instance = (
            lambda obj: f'{obj.name} — ${obj.base_rate}'
        )
        if instance:
            self.fields['start_at'].initial = format_datetime_input(instance.scheduled_start)
            self.fields['end_at'].initial = format_datetime_input(instance.scheduled_end)
            self.fields['notes'].initial = instance.notes
            self.client = instance.client
            if instance.business_service_id:
                service_field.initial = instance.business_service_id
                service_field.queryset = (
                    BusinessService.objects.filter(tenant=workspace)
                    .filter(
                        models.Q(is_active=True) | models.Q(pk=instance.business_service_id),
                    )
                    .order_by('target_category', 'name')
                )
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
            return cleaned

        cleaned['scheduled_start'] = scheduled_start
        cleaned['scheduled_end'] = scheduled_end

        if not self.instance:
            self._validate_standard_stay_readiness()
            if self.errors:
                return cleaned
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

        cleaned['occurrences'] = self._build_occurrences(cleaned)
        if self._occurrence_limit_exceeded(cleaned):
            return cleaned
        self._validate_occurrence_capacity(
            cleaned['occurrences'],
            business_service=cleaned.get('business_service'),
        )
        return cleaned

    def _validate_standard_stay_readiness(self) -> None:
        if not self.client:
            return
        for message in self.client.standard_stay_blockers():
            self.add_error(None, message)

    def _build_occurrences(self, cleaned) -> list[tuple]:
        start = cleaned['scheduled_start']
        end = cleaned['scheduled_end']
        if self.instance:
            return [(start, end)]
        frequency = cleaned.get('repeat_frequency') or FREQUENCY_NONE
        return generate_repeat_occurrences(
            start,
            end,
            frequency=frequency,
            interval=cleaned.get('repeat_interval') or 1,
            end_type=cleaned.get('repeat_end_type') or END_AFTER,
            count=cleaned.get('repeat_count') or 1,
            until=cleaned.get('repeat_until_dt'),
        )

    def _occurrence_limit_exceeded(self, cleaned) -> bool:
        occurrences = cleaned['occurrences']
        frequency = cleaned.get('repeat_frequency') or FREQUENCY_NONE
        if frequency == FREQUENCY_NONE:
            return False
        if len(occurrences) > MAX_OCCURRENCES:
            self.add_error(
                'repeat_ends',
                f'Repeat is limited to {MAX_OCCURRENCES} visits.',
            )
            return True
        until_dt = cleaned.get('repeat_until_dt')
        if (
            cleaned.get('repeat_end_type') == END_ON
            and until_dt is not None
            and len(occurrences) >= MAX_OCCURRENCES
        ):
            last_date = timezone.localtime(occurrences[-1][0]).date()
            until_date = timezone.localtime(until_dt).date()
            if until_date > last_date:
                self.add_error(
                    'repeat_ends',
                    f'Repeat is limited to {MAX_OCCURRENCES} visits. '
                    f'Choose a closer end date or a number from 1 to {MAX_OCCURRENCES}.',
                )
                return True
        return False

    def _validate_occurrence_capacity(
        self,
        occurrences: list[tuple],
        *,
        business_service=None,
    ) -> None:
        if not self.client:
            self.add_error(None, 'Dog is required to schedule a visit.')
            return
        exclude_id = getattr(self.instance, 'pk', None)
        for occ_start, occ_end in occurrences:
            clash = overlapping_dog_visit(
                self.client.pk,
                occ_start,
                occ_end,
                exclude_visit_id=exclude_id,
            )
            if clash:
                self.add_error(
                    None,
                    f'Cannot schedule {format_datetime_display(occ_start)}: '
                    f'{self.client.dog_name} is already booked {clash.schedule_display}.',
                )
                return
            probe = Visit(
                pk=exclude_id,
                client=self.client,
                scheduled_start=occ_start,
                scheduled_end=occ_end,
                business_service=business_service,
            )
            capacity = check_visit_capacity(probe)
            if capacity['status'] == 'blocked':
                self.add_error(
                    None,
                    f'Cannot schedule {format_datetime_display(occ_start)}: {capacity["message"]}',
                )
                return

    def save(self) -> Visit:
        created = self.save_all()
        return created[0]

    @transaction.atomic
    def save_all(self) -> list[Visit]:
        if not self.client:
            raise ValidationError('Dog is required to schedule a visit.')
        notes = self.cleaned_data.get('notes', '')
        business_service = self.cleaned_data['business_service']
        occurrences = self.cleaned_data['occurrences']
        created: list[Visit] = []
        series = None
        frequency = self.cleaned_data.get('repeat_frequency') or FREQUENCY_NONE

        if not self.instance and frequency != FREQUENCY_NONE:
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
                visit.business_service = business_service
                visit.save(
                    skip_capacity=True,
                    update_fields=[
                        'scheduled_start', 'scheduled_end', 'notes',
                        'business_service', 'updated_at',
                    ],
                )
            else:
                visit = Visit(
                    client=self.client,
                    scheduled_start=occ_start,
                    scheduled_end=occ_end,
                    notes=notes,
                    business_service=business_service,
                    series=series,
                    series_position=index if series else None,
                )
                visit.save(skip_capacity=True)
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
        camera = cleaned.get('photo_camera')
        gallery = cleaned.get('photo_gallery')
        video = cleaned.get('video')
        if camera and gallery:
            raise ValidationError('Choose a camera photo or a gallery photo, not both.')
        photo = camera or gallery
        media_count = sum(bool(x) for x in (photo, video))
        if media_count > 1:
            raise ValidationError('Submit one photo or one video.')
        if media_count == 0:
            raise ValidationError('Capture or choose a photo, or choose a video from your gallery.')
        cleaned['uploaded_file'] = photo or video
        cleaned['media_kind'] = 'photo' if photo else 'video'
        self._clean_coordinates(cleaned)
        return cleaned

    def _clean_coordinates(self, cleaned) -> None:
        lat = self._parse_coordinate_field(cleaned, 'latitude', Decimal('-90'), Decimal('90'))
        lng = self._parse_coordinate_field(cleaned, 'longitude', Decimal('-180'), Decimal('180'))
        if (lat is None) ^ (lng is None):
            if 'latitude' not in self.errors and 'longitude' not in self.errors:
                missing = 'longitude' if lat is not None else 'latitude'
                self.add_error(
                    missing,
                    'Latitude and longitude must both be set, or both left blank.',
                )

    def _parse_coordinate_field(self, cleaned, field, minimum, maximum) -> Decimal | None:
        raw = (cleaned.get(field) or '').strip()
        if not raw:
            cleaned[field] = ''
            return None
        try:
            coord = Decimal(raw)
        except (InvalidOperation, ValueError):
            self.add_error(field, 'Enter a valid coordinate.')
            return None
        if coord < minimum or coord > maximum:
            self.add_error(field, 'Enter a valid coordinate.')
            return None
        cleaned[field] = coord
        return coord


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