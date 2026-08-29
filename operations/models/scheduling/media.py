from django.db import models
from django.utils import timezone
from operations.models.base import TenantAwareModel


def timeline_asset_upload_path(instance: models.Model, filename: str) -> str:
    """Store new media under timeline/assets/YYYY/MM/DD/."""
    when = getattr(instance, 'captured_at', None) or timezone.now()
    return when.strftime('timeline/assets/%Y/%m/%d/') + filename


def timeline_upload_path(instance, filename: str) -> str:
    """Legacy upload path kept for migration 0008 compatibility."""
    visit_id = getattr(instance, 'visit_id', None) or 'legacy'
    return f'timeline/{visit_id}/{filename}'


class TimelineMediaAsset(TenantAwareModel):
    class MediaType(models.TextChoices):
        PHOTO = 'photo', 'Photo'
        VIDEO = 'video', 'Video'

    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    photo_high_res = models.ImageField(
        upload_to=timeline_asset_upload_path,
        blank=True,
        help_text='Uncompressed master image for customer printing.',
    )
    photo_thumbnail = models.ImageField(
        upload_to=timeline_asset_upload_path,
        blank=True,
        help_text='Web-optimized WebP thumbnail for timeline display.',
    )
    video_file = models.FileField(
        upload_to=timeline_asset_upload_path,
        blank=True,
        help_text='Gallery-selected video (no live capture).',
    )
    caption_notes = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_used_fallback = models.BooleanField(default=False)
    location_fallback_label = models.CharField(max_length=300, blank=True)
    captured_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        help_text='Exact capture/upload time — preserved when forwarded.',
    )
    original_visit = models.ForeignKey(
        'operations.Visit',
        on_delete=models.PROTECT,
        related_name='originated_timeline_assets',
        help_text='First visit this moment was logged against.',
    )

    class Meta:
        ordering = ['-captured_at']

    def __str__(self):
        return f'{self.get_media_type_display()} @ {self.captured_at:%Y-%m-%d %H:%M}'