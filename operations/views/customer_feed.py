from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from operations.models import ClientProfile, SharedMediaLink, VisitTimelineEvent
from operations.services.feed_slugs import generate_unique_share_token
from operations.services.share_preview import build_share_preview_context
from operations.services.feed_access import get_or_set_visitor_id, log_feed_access
from operations.services.feed_emojis import reaction_choices_for_feed, standard_emoji_label
from operations.services.feed_interactions import (
    DISPLAY_NAME_COOKIE,
    DISPLAY_NAME_MAX_AGE,
    FeedInteractionError,
    add_comment,
    comments_for_assets,
    get_or_create_share_link,
    reaction_counts_for_assets,
    record_share_view,
    set_reaction,
    share_url_for_link,
    visitor_reactions_for_assets,
)


def _resolve_feed_client(feed_secret: str, feed_dog_slug: str) -> ClientProfile:
    client = get_object_or_404(
        ClientProfile.objects.select_related(),
        feed_secret=feed_secret,
    )
    client.ensure_feed_credentials()
    if client.feed_dog_slug != feed_dog_slug:
        raise Http404('Feed link does not match this dog.')
    return client


def _feed_private_headers(response):
    response['X-Robots-Tag'] = 'noindex, nofollow'
    response['Cache-Control'] = 'private, no-store'
    return response


def _reaction_summary(counts: dict[str, int]) -> str:
    parts = [f'{standard_emoji_label(key)} {count}' for key, count in counts.items()]
    return ' · '.join(parts)


def _build_event_rows(client, events, visitor_id: str, request):
    asset_ids = [event.media_asset_id for event in events]
    reaction_counts = reaction_counts_for_assets(asset_ids)
    visitor_reactions = visitor_reactions_for_assets(asset_ids, visitor_id)
    comments_by_asset = comments_for_assets(asset_ids)
    rows = []
    for event in events:
        link = get_or_create_share_link(client=client, asset_id=event.media_asset_id)
        counts = reaction_counts.get(event.media_asset_id, {})
        rows.append({
            'event': event,
            'reactions': counts,
            'reaction_summary': _reaction_summary(counts),
            'my_reaction': visitor_reactions.get(event.media_asset_id, ''),
            'comments': comments_by_asset.get(event.media_asset_id, []),
            'comment_count': len(comments_by_asset.get(event.media_asset_id, [])),
            'share_url': share_url_for_link(link, request=request),
        })
    return rows


def _redirect_feed(client: ClientProfile, *, asset_id: int | None = None):
    url = reverse(
        'operations:customer_feed',
        kwargs={
            'feed_secret': client.feed_secret,
            'feed_dog_slug': client.feed_dog_slug,
        },
    )
    if asset_id:
        url = f'{url}#moment-{asset_id}'
    return redirect(url)


@require_GET
def customer_feed(request, feed_secret: str, feed_dog_slug: str):
    """Customer feed — secret link, reactions, comments, compact share menu per moment."""
    client = _resolve_feed_client(feed_secret, feed_dog_slug)

    events = list(
        VisitTimelineEvent.objects.filter(visit__client=client)
        .select_related('media_asset', 'visit', 'source_event__visit__client')
        .order_by('-media_asset__captured_at', '-shared_at')
    )

    visitor_id = get_or_set_visitor_id(request)
    response = render(request, 'operations/customer_feed.html', {
        'dog': client,
        'event_rows': _build_event_rows(client, events, visitor_id, request),
        'reaction_choices': reaction_choices_for_feed(),
        'display_name': request.COOKIES.get(DISPLAY_NAME_COOKIE, ''),
    })
    _feed_private_headers(response)
    get_or_set_visitor_id(request, response)
    log_feed_access(
        client=client,
        visitor_id=visitor_id,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
    return response


@require_POST
def customer_feed_react(request, feed_secret: str, feed_dog_slug: str, asset_id: int):
    client = _resolve_feed_client(feed_secret, feed_dog_slug)
    visitor_id = get_or_set_visitor_id(request)
    emoji = (request.POST.get('emoji') or '').strip()
    try:
        set_reaction(
            client=client,
            asset_id=asset_id,
            visitor_id=visitor_id,
            emoji=emoji,
        )
    except FeedInteractionError:
        pass
    return _redirect_feed(client, asset_id=asset_id)


@require_POST
def customer_feed_comment(request, feed_secret: str, feed_dog_slug: str, asset_id: int):
    client = _resolve_feed_client(feed_secret, feed_dog_slug)
    visitor_id = get_or_set_visitor_id(request)
    display_name = (request.POST.get('display_name') or '').strip()
    text = request.POST.get('text', '')
    try:
        add_comment(
            client=client,
            asset_id=asset_id,
            visitor_id=visitor_id,
            text=text,
            display_name=display_name,
        )
    except FeedInteractionError:
        return _redirect_feed(client, asset_id=asset_id)

    response = _redirect_feed(client, asset_id=asset_id)
    if display_name:
        response.set_cookie(
            DISPLAY_NAME_COOKIE,
            display_name[:80],
            max_age=DISPLAY_NAME_MAX_AGE,
            httponly=False,
            samesite='Lax',
            secure=request.is_secure(),
        )
    return response


@require_GET
def customer_feed_redirect(request, feed_secret: str):
    client = get_object_or_404(ClientProfile, feed_secret=feed_secret)
    client.ensure_feed_credentials()
    return redirect('operations:customer_feed', feed_secret=client.feed_secret, feed_dog_slug=client.feed_dog_slug)


@require_GET
def public_feed_share(request, share_token: str):
    """Anonymous single-moment page — /feed/share/<token>/"""
    link = get_object_or_404(
        SharedMediaLink.objects.select_related('media_asset', 'client'),
        share_token=share_token,
    )
    record_share_view(link)
    response = render(
        request,
        'operations/public_photo_share.html',
        build_share_preview_context(request, link),
    )
    return response


@require_GET
def public_shared_media_legacy(request, share_id):
    """Redirect old /share/photo/<uuid>/ links to /feed/share/<token>/."""
    link = get_object_or_404(SharedMediaLink, pk=share_id)
    if not link.share_token:
        link.share_token = generate_unique_share_token()
        link.save(update_fields=['share_token'])
    return redirect('operations:public_feed_share', share_token=link.share_token)