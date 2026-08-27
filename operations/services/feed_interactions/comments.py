from django.utils import timezone

from operations.models.customers import ClientProfile
from operations.models.scheduling import MediaComment
from operations.services.feed_interactions.constants import (
    COMMENT_MAX_LENGTH,
    COMMENTS_PER_VISITOR_PER_DAY,
)
from operations.services.feed_interactions.errors import FeedInteractionError
from operations.services.feed_interactions.queries import asset_belongs_to_client


def add_comment(
    *,
    client: ClientProfile,
    asset_id: int,
    visitor_id: str,
    text: str,
    display_name: str = '',
) -> MediaComment:
    asset = asset_belongs_to_client(asset_id, client)
    cleaned = (text or '').strip()
    if not cleaned:
        raise FeedInteractionError('Write a comment before posting.')
    if len(cleaned) > COMMENT_MAX_LENGTH:
        raise FeedInteractionError(f'Comments must be {COMMENT_MAX_LENGTH} characters or fewer.')

    since = timezone.now() - timezone.timedelta(days=1)
    recent = MediaComment.objects.filter(
        client=client,
        visitor_id=visitor_id,
        created_at__gte=since,
    ).count()
    if recent >= COMMENTS_PER_VISITOR_PER_DAY:
        raise FeedInteractionError('Comment limit reached for today — try again tomorrow.')

    name = (display_name or '').strip()[:80] or 'Guest'
    return MediaComment.objects.create(
        media_asset=asset,
        client=client,
        visitor_id=visitor_id,
        display_name=name,
        text=cleaned,
    )
