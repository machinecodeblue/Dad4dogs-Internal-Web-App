import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from operations.capacity import check_visit_capacity
from operations.pricing import calculate_fee

from .customers import ClientProfile


class VisitSeries(models.Model):
    """Links recurring visits created together (Google Calendar–style repeat)."""
    client = models.ForeignKey(
        ClientProfile, on_delete=models.CASCADE, related_name='visit_series',
    )
    frequency = models.CharField(max_length=20)
    interval = models.PositiveSmallIntegerField(default=1)
    end_type = models.CharField(max_length=10)
    total_occurrences = models.PositiveSmallIntegerField()
    until = models.DateTimeField(null=True, blank=True)
    anchor_start = models.DateTimeField(
        help_text='Start of the first occurrence (template for the series).',
    )
    anchor_end = models.DateTimeField(
        help_text='End of the first occurrence (template for the series).',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'visit series'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.client.dog_name} — {self.frequency} × {self.total_occurrences}'

    @property
    def label(self) -> str:
        from operations.services.visit_repeat import repeat_summary

        visits = list(self.visits.order_by('scheduled_start'))
        if not visits:
            return f'Repeat ({self.total_occurrences})'
        pairs = [(v.scheduled_start, v.scheduled_end) for v in visits]
        return repeat_summary(pairs, self.frequency, self.interval)


class Visit(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        CHECKED_IN = 'checked_in', 'Checked In'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    client = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='visits')
    series = models.ForeignKey(
        VisitSeries,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='visits',
    )
    series_position = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='1-based index within the repeat series.',
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    calculated_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fee_breakdown = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    confirmation_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the customer was emailed this booking confirmation.',
    )
    cloned_from = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='clones',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start']

    def __str__(self):
        return f'{self.client.dog_name} — {self.scheduled_start:%Y-%m-%d %H:%M}'

    def clean(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValidationError('Scheduled end must be after scheduled start.')

        capacity = check_visit_capacity(self)
        if capacity['status'] == 'blocked':
            raise ValidationError(capacity['message'])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def check_in(self):
        self.actual_arrival = timezone.now()
        self.status = self.Status.CHECKED_IN
        self.save(update_fields=['actual_arrival', 'status', 'updated_at'])

    def check_out(self):
        self.actual_departure = timezone.now()
        arrival = self.actual_arrival or self.scheduled_start
        fee, breakdown = calculate_fee(arrival, self.actual_departure)
        self.calculated_fee = fee
        self.fee_breakdown = breakdown
        self.status = self.Status.COMPLETED
        self.save(update_fields=[
            'actual_departure', 'calculated_fee', 'fee_breakdown', 'status', 'updated_at',
        ])

    def clone_to_date(self, new_date):
        """Clone duration and time-of-day configuration to a new calendar date."""
        start = self.scheduled_start
        end = self.scheduled_end
        duration = end - start
        new_start = start.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        new_end = new_start + duration
        return Visit.objects.create(
            client=self.client,
            scheduled_start=new_start,
            scheduled_end=new_end,
            cloned_from=self,
            notes=f'Cloned from visit on {start:%Y-%m-%d}',
        )

    @property
    def duration_hours(self) -> float:
        return (self.scheduled_end - self.scheduled_start).total_seconds() / 3600

    @property
    def schedule_display(self) -> str:
        start = timezone.localtime(self.scheduled_start)
        end = timezone.localtime(self.scheduled_end)
        if start.date() == end.date():
            return (
                f'{start:%b %d, %Y} {start:%I:%M %p} – {end:%I:%M %p}'
            )
        return (
            f'{start:%b %d, %Y} {start:%I:%M %p} – '
            f'{end:%b %d, %Y} {end:%I:%M %p}'
        )

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.SCHEDULED

    @property
    def accepts_timeline_events(self) -> bool:
        return self.status == self.Status.CHECKED_IN


def timeline_asset_upload_path(instance: 'TimelineMediaAsset', filename: str) -> str:
    return f'timeline/assets/{instance.pk or "new"}/{filename}'


def timeline_upload_path(instance, filename: str) -> str:
    """Legacy upload path kept for migration 0008 compatibility."""
    visit_id = getattr(instance, 'visit_id', None) or 'legacy'
    return f'timeline/{visit_id}/{filename}'


class TimelineMediaAsset(models.Model):
    """
    Immutable capture payload — one file set shared across multiple visit timelines.
    """
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
        editable=False,
        help_text='Exact capture/upload time — preserved when forwarded.',
    )
    original_visit = models.ForeignKey(
        Visit,
        on_delete=models.PROTECT,
        related_name='originated_timeline_assets',
        help_text='First visit this moment was logged against.',
    )

    class Meta:
        ordering = ['-captured_at']

    def __str__(self):
        return f'{self.get_media_type_display()} @ {self.captured_at:%Y-%m-%d %H:%M}'


class VisitTimelineEvent(models.Model):
    """
    Links a shared TimelineMediaAsset to one visit's contemporaneous record.
    Forwarding creates new rows pointing at the same asset.
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


class MediaReaction(models.Model):
    """Per-browser emoji reaction on a timeline moment (no customer login)."""

    class Emoji(models.TextChoices):
        LIKE = 'like', '👍'
        LOVE = 'love', '❤️'
        HAHA = 'haha', '😂'
        WOW = 'wow', '😮'
        SAD = 'sad', '😢'

    media_asset = models.ForeignKey(
        TimelineMediaAsset,
        on_delete=models.CASCADE,
        related_name='reactions',
    )
    visitor_id = models.CharField(
        max_length=36,
        help_text='Anonymous browser ID from dad4dogs_feed_vid cookie.',
    )
    emoji = models.CharField(max_length=10, choices=Emoji.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['media_asset', 'visitor_id'],
                name='unique_reaction_per_visitor_per_asset',
            ),
        ]

    def __str__(self):
        return f'{self.get_emoji_display()} on asset {self.media_asset_id}'


class MediaComment(models.Model):
    """Visitor comment on a timeline moment — display name only, no account."""

    media_asset = models.ForeignKey(
        TimelineMediaAsset,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='feed_comments',
        help_text='Dog feed where the comment was posted.',
    )
    visitor_id = models.CharField(max_length=36)
    display_name = models.CharField(max_length=80, default='Guest')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.display_name}: {self.text[:40]}'


class SharedMediaLink(models.Model):
    """
    Opaque public link for a single moment — does not expose the private feed URL.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share_token = models.CharField(
        max_length=24,
        unique=True,
        blank=True,
        help_text='Public URL key — /feed/share/<share_token>/',
    )
    media_asset = models.ForeignKey(
        TimelineMediaAsset,
        on_delete=models.CASCADE,
        related_name='share_links',
    )
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='shared_media_links',
    )
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['media_asset', 'client'],
                name='unique_share_link_per_asset_per_client',
            ),
        ]

    def __str__(self):
        return f'Share {self.id} — {self.client.dog_name}'


class PendingCalendarEvent(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    event_uid = models.CharField(max_length=255, unique=True)
    summary = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    matched_client = models.ForeignKey(
        ClientProfile, null=True, blank=True, on_delete=models.SET_NULL,
    )
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_datetime']

    def __str__(self):
        return self.summary