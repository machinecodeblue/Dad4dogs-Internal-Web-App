from django.utils import timezone

from operations.models import ClientProfile, MediaComment, MediaReaction, VisitTimelineEvent
from operations.services.feed_emojis import standard_emoji_label


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
            'emoji_label': standard_emoji_label(reaction.emoji),
            'asset_id': reaction.media_asset_id,
        })

    for payload in dogs.values():
        payload['items'].sort(key=lambda row: row['at'], reverse=True)
        payload['items'] = payload['items'][:12]

    return {
        'dogs': dogs,
        'server_time': timezone.now().isoformat(),
    }
