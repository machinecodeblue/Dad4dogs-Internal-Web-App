from django.db import models
from operations.models.base import TenantAwareModel
from .media import TimelineMediaAsset
from .visits import Visit


class VisitTimelineEvent(TenantAwareModel):
    """
    Links a shared TimelineMediaAsset to one visit's contemporaneous record.
    """
    visit = models.ForeignKey(
        Visit,
        on_delete=models.CASCADE,
        related_name='timeline_events',
    )
    media_asset = models.ForeignKey(
        TimelineMediaAsset,
        on_delete=models.CASCADE,
        related_name='visit_links',
    )
    source_event = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='forwarded_copies',
        help_text="Set when this row was forwarded from another dog's timeline.",
    )
    shared_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text='When this moment was attached to this visit.',
    )

    class Meta:
        ordering = ['-media_asset__captured_at', '-shared_at']
        constraints = [
            models.UniqueConstraint(
                fields=['visit', 'media_asset'],
                name='unique_timeline_asset_per_visit',
            ),
        ]

    def __str__(self):
        return f'{self.visit.client.dog_name} — {self.media_asset}'

    @property
    def captured_at(self):
        return self.media_asset.captured_at

    @property
    def media_type(self):
        return self.media_asset.media_type

    @property
    def photo_high_res(self):
        return self.media_asset.photo_high_res

    @property
    def photo_thumbnail(self):
        return self.media_asset.photo_thumbnail

    @property
    def video_file(self):
        return self.media_asset.video_file

    @property
    def caption_notes(self):
        return self.media_asset.caption_notes

    @property
    def latitude(self):
        return self.media_asset.latitude

    @property
    def longitude(self):
        return self.media_asset.longitude

    @property
    def location_used_fallback(self):
        return self.media_asset.location_used_fallback

    @property
    def location_fallback_label(self):
        return self.media_asset.location_fallback_label

    @property
    def is_forward(self) -> bool:
        return self.source_event_id is not None

    @property
    def dog_name(self) -> str:
        return self.visit.client.dog_name

    @property
    def owner_email(self) -> str:
        return self.visit.client.owner_email