from django.http import HttpResponse
from django.urls import reverse

from operations.models import SharedMediaLink
from operations.services.feed_interactions import (
    DISPLAY_NAME_COOKIE,
    DISPLAY_NAME_MAX_AGE,
    comments_for_assets,
    generate_unique_share_token,
    reaction_counts_for_assets,
    share_url_for_link,
    standard_emoji_label,
    visitor_reactions_for_assets,
)


def apply_feed_private_headers(response: HttpResponse) -> HttpResponse:
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Cache-Control'] = 'private, no-store'
    return response


def set_display_name_cookie(response: HttpResponse, request, display_name: str) -> None:
    if display_name:
        response.set_cookie(
            DISPLAY_NAME_COOKIE,
            display_name[:80],
            max_age=DISPLAY_NAME_MAX_AGE,
            httponly=False,
            samesite='Lax',
            secure=request.is_secure(),
        )


def reaction_summary(counts: dict[str, int]) -> str:
    parts = [f'{standard_emoji_label(key)} {count}' for key, count in counts.items()]
    return ' · '.join(parts)


def build_feed_event_rows(client, events, visitor_id: str, request):
    asset_ids = [event.media_asset_id for event in events]
    if not asset_ids:
        return []

    # 1. Bulk load reactions and comments
    reaction_counts = reaction_counts_for_assets(asset_ids)
    visitor_reactions = visitor_reactions_for_assets(asset_ids, visitor_id)
    comments_by_asset = comments_for_assets(asset_ids)

    # 2. Bulk load existing share links to eliminate N+1 queries
    existing_links = {
        link.media_asset_id: link
        for link in SharedMediaLink.objects.filter(client=client, media_asset_id__in=asset_ids)
    }

    # 3. Create any missing share links in bulk
    missing_asset_ids = [aid for aid in asset_ids if aid not in existing_links]
    if missing_asset_ids:
        new_links = [
            SharedMediaLink(
                client=client,
                media_asset_id=aid,
                share_token=generate_unique_share_token(),
            )
            for aid in missing_asset_ids
        ]
        SharedMediaLink.objects.bulk_create(new_links, ignore_conflicts=True)
        for link in SharedMediaLink.objects.filter(client=client, media_asset_id__in=missing_asset_ids):
            existing_links[link.media_asset_id] = link

    # 4. Assemble rows
    rows = []
    for event in events:
        link = existing_links.get(event.media_asset_id)
        counts = reaction_counts.get(event.media_asset_id, {})
        rows.append({
            'event': event,
            'reactions': counts,
            'reaction_summary': reaction_summary(counts),
            'my_reaction': visitor_reactions.get(event.media_asset_id, ''),
            'comments': comments_by_asset.get(event.media_asset_id, []),
            'comment_count': len(comments_by_asset.get(event.media_asset_id, [])),
            'share_url': share_url_for_link(link, request=request) if link else '',
        })
    return rows