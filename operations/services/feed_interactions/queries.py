from django.db.models import Count

from operations.models import (
    ClientProfile,
    MediaComment,
    MediaReaction,
    TimelineMediaAsset,
    VisitTimelineEvent,
)
from operations.services.feed_interactions.errors import FeedInteractionError


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
