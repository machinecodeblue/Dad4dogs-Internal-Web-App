import uuid

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from operations.models import (
    ClientProfile,
    MediaComment,
    MediaReaction,
    SharedMediaLink,
    TimelineMediaAsset,
    VisitTimelineEvent,
)
from operations.services.feed_slugs import generate_unique_share_token

COMMENT_MAX_LENGTH = 500
COMMENTS_PER_VISITOR_PER_DAY = 30
DISPLAY_NAME_COOKIE = 'dad4dogs_feed_name'
DISPLAY_NAME_MAX_AGE = 60 * 60 * 24 * 365


class FeedInteractionError(Exception):
    """Raised when a feed reaction, comment, or share is not allowed."""


def asset_belongs_to_client(asset_id: int, client: ClientProfile) -> TimelineMediaAsset:
    asset = TimelineMediaAsset.objects.filter(pk=asset_id).first()
    if not asset:
        raise FeedInteractionError('This moment was not found.')
    linked = VisitTimelineEvent.objects.filter(
        visit__client=client,
        media_asset_id=asset_id,
    ).exists()
    if not linked:
        raise FeedInteractionError('This moment is not on this feed.')
    return asset


def reaction_counts_for_assets(asset_ids: list[int]) -> dict[int, dict[str, int]]:
    if not asset_ids:
        return {}
    rows = (
        MediaReaction.objects.filter(media_asset_id__in=asset_ids)
        .values('media_asset_id', 'emoji')
        .annotate(total=Count('id'))
    )
    summary: dict[int, dict[str, int]] = {}
    for row in rows:
        bucket = summary.setdefault(row['media_asset_id'], {})
        bucket[row['emoji']] = row['total']
    return summary


def visitor_reactions_for_assets(asset_ids: list[int], visitor_id: str) -> dict[int, str]:
    if not asset_ids or not visitor_id:
        return {}
    return dict(
        MediaReaction.objects.filter(
            media_asset_id__in=asset_ids,
            visitor_id=visitor_id,
        ).values_list('media_asset_id', 'emoji')
    )


def comments_for_assets(asset_ids: list[int]) -> dict[int, list[MediaComment]]:
    if not asset_ids:
        return {}
    comments = MediaComment.objects.filter(media_asset_id__in=asset_ids).order_by('created_at')
    grouped: dict[int, list[MediaComment]] = {}
    for comment in comments:
        grouped.setdefault(comment.media_asset_id, []).append(comment)
    return grouped


def set_reaction(
    *,
    client: ClientProfile,
    asset_id: int,
    visitor_id: str,
    emoji: str,
) -> MediaReaction | None:
    asset = asset_belongs_to_client(asset_id, client)
    if emoji == '':
        MediaReaction.objects.filter(media_asset=asset, visitor_id=visitor_id).delete()
        return None
    if emoji not in MediaReaction.Emoji.values:
        raise FeedInteractionError('Choose a reaction from the emoji bar.')
    reaction, _ = MediaReaction.objects.update_or_create(
        media_asset=asset,
        visitor_id=visitor_id,
        defaults={'emoji': emoji},
    )
    return reaction


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


def get_or_create_share_link(*, client: ClientProfile, asset_id: int) -> SharedMediaLink:
    asset = asset_belongs_to_client(asset_id, client)
    link, created = SharedMediaLink.objects.get_or_create(
        media_asset=asset,
        client=client,
    )
    if created or not link.share_token:
        link.share_token = generate_unique_share_token()
        link.save(update_fields=['share_token'])
    return link


def share_url_for_link(link: SharedMediaLink, *, request=None) -> str:
    from django.urls import reverse

    path = reverse('operations:public_feed_share', kwargs={'share_token': link.share_token})
    if request is not None:
        return request.build_absolute_uri(path)
    from django.conf import settings

    base = getattr(settings, 'PUBLIC_SITE_URL', '').rstrip('/')
    if base:
        return f'{base}{path}'
    return path


def record_share_view(link: SharedMediaLink) -> None:
    link.view_count += 1
    link.save(update_fields=['view_count'])


def build_checkin_feed_activity(
    client_ids: list[int],
    *,
    since=None,
) -> dict:
    """
    Recent owner/family reactions and comments for David's check-in screen.
    Customers identify via feed visitor cookie — not Django session.
    """
    if not client_ids:
        return {'dogs': {}, 'server_time': timezone.now().isoformat()}

    if since is None:
        since = timezone.now() - timezone.timedelta(hours=48)

    emoji_labels = dict(MediaReaction.Emoji.choices)
    dogs: dict[str, dict] = {}

    for comment in (
        MediaComment.objects.filter(client_id__in=client_ids, created_at__gte=since)
        .select_related('client')
        .order_by('-created_at')[:80]
    ):
        bucket = dogs.setdefault(str(comment.client_id), {
            'dog_name': comment.client.dog_name,
            'items': [],
        })
        bucket['items'].append({
            'type': 'comment',
            'at': comment.created_at.isoformat(),
            'display_name': comment.display_name,
            'text': comment.text,
            'asset_id': comment.media_asset_id,
        })

    asset_ids = VisitTimelineEvent.objects.filter(
        visit__client_id__in=client_ids,
    ).values_list('media_asset_id', flat=True).distinct()

    for reaction in (
        MediaReaction.objects.filter(
            media_asset_id__in=asset_ids,
            updated_at__gte=since,
        )
        .select_related('media_asset')
        .order_by('-updated_at')[:80]
    ):
        client_id = (
            VisitTimelineEvent.objects.filter(media_asset_id=reaction.media_asset_id)
            .values_list('visit__client_id', flat=True)
            .first()
        )
        if client_id not in client_ids:
            continue
        client = ClientProfile.objects.filter(pk=client_id).first()
        if not client:
            continue
        bucket = dogs.setdefault(str(client_id), {
            'dog_name': client.dog_name,
            'items': [],
        })
        bucket['items'].append({
            'type': 'reaction',
            'at': reaction.updated_at.isoformat(),
            'emoji': reaction.emoji,
            'emoji_label': emoji_labels.get(reaction.emoji, reaction.emoji),
            'asset_id': reaction.media_asset_id,
        })

    for payload in dogs.values():
        payload['items'].sort(key=lambda row: row['at'], reverse=True)
        payload['items'] = payload['items'][:12]

    return {
        'dogs': dogs,
        'server_time': timezone.now().isoformat(),
    }