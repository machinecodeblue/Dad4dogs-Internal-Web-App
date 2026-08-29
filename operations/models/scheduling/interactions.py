import uuid
from django.db import models
from operations.models.base import TenantAwareModel
from operations.models.customers import ClientProfile
from .media import TimelineMediaAsset


class MediaReaction(TenantAwareModel):
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


class MediaComment(TenantAwareModel):
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


class SharedMediaLink(TenantAwareModel):
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