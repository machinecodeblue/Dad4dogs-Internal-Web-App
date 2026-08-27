from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from operations.models import ClientProfile, VisitTimelineEvent
from operations.services.feed_interactions import (
    DISPLAY_NAME_COOKIE,
    FeedInteractionError,
    add_comment,
    get_or_set_visitor_id,
    log_feed_access,
    reaction_choices_for_feed,
    set_reaction,
)
from operations.views.feed.helpers import (
    apply_feed_private_headers,
    build_feed_event_rows,
    set_display_name_cookie,
)


def _resolve_feed_client(feed_secret: str, feed_dog_slug: str) -> ClientProfile:
    client = get_object_or_404(ClientProfile.objects.select_related(), feed_secret=feed_secret)
    client.ensure_feed_credentials()
    if client.feed_dog_slug != feed_dog_slug:
        raise Http404('Feed link does not match this dog.')
    return client


def _redirect_feed(client: ClientProfile, *, asset_id: int | None = None):
    url = reverse('operations:customer_feed', kwargs={
        'feed_secret': client.feed_secret,
        'feed_dog_slug': client.feed_dog_slug,
    })
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
        'event_rows': build_feed_event_rows(client, events, visitor_id, request),
        'reaction_choices': reaction_choices_for_feed(),
        'display_name': request.COOKIES.get(DISPLAY_NAME_COOKIE, ''),
    })
    apply_feed_private_headers(response)
    get_or_set_visitor_id(request, response)
    log_feed_access(client=client, visitor_id=visitor_id, user_agent=request.META.get('HTTP_USER_AGENT', ''))
    return response


@require_POST
def customer_feed_react(request, feed_secret: str, feed_dog_slug: str, asset_id: int):
    client = _resolve_feed_client(feed_secret, feed_dog_slug)
    visitor_id = get_or_set_visitor_id(request)
    emoji = (request.POST.get('emoji') or '').strip()
    try:
        set_reaction(client=client, asset_id=asset_id, visitor_id=visitor_id, emoji=emoji)
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
        add_comment(client=client, asset_id=asset_id, visitor_id=visitor_id, text=text, display_name=display_name)
    except FeedInteractionError:
        return _redirect_feed(client, asset_id=asset_id)

    response = _redirect_feed(client, asset_id=asset_id)
    set_display_name_cookie(response, request, display_name)
    return response


@require_GET
def customer_feed_redirect(request, feed_secret: str):
    client = get_object_or_404(ClientProfile, feed_secret=feed_secret)
    client.ensure_feed_credentials()
    return redirect('operations:customer_feed', feed_secret=client.feed_secret, feed_dog_slug=client.feed_dog_slug)