from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from operations.models import Visit


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
    """Share an existing timeline moment with other active checked-in dogs."""

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