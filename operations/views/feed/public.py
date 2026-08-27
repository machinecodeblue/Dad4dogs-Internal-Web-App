from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from operations.models import SharedMediaLink
from operations.services.feed_interactions import (
    DISPLAY_NAME_COOKIE,
    FeedInteractionError,
    add_comment,
    build_share_preview_context,
    comments_for_assets,
    generate_unique_share_token,
    get_or_set_visitor_id,
    reaction_choices_for_feed,
    reaction_counts_for_assets,
    record_share_view,
    set_reaction,
    share_download_field,
    share_download_filename,
    share_download_page_url,
    share_url_for_link,
    visitor_reactions_for_assets,
)
from operations.views.feed.helpers import reaction_summary, set_display_name_cookie


def _resolve_share_link(share_token: str) -> SharedMediaLink:
    return get_object_or_404(
        SharedMediaLink.objects.select_related('media_asset', 'client'),
        share_token=share_token,
    )


def _redirect_share(share_token: str, *, open_comments: bool = False):
    url = reverse('operations:public_feed_share', kwargs={'share_token': share_token})
    params = ['posted=1']
    if open_comments:
        params.append('comments=1')
    return redirect(f'{url}?{"&".join(params)}')


def _share_page_context(request, link: SharedMediaLink, visitor_id: str) -> dict:
    context = build_share_preview_context(request, link)
    asset_id = link.media_asset_id
    counts = reaction_counts_for_assets([asset_id]).get(asset_id, {})
    comments = comments_for_assets([asset_id]).get(asset_id, [])
    download_url, download_filename = share_download_page_url(request, link)
    context.update({
        'asset_id': asset_id,
        'reaction_summary': reaction_summary(counts),
        'my_reaction': visitor_reactions_for_assets([asset_id], visitor_id).get(asset_id, ''),
        'comments': comments,
        'comment_count': len(comments),
        'reaction_choices': reaction_choices_for_feed(),
        'display_name': request.COOKIES.get(DISPLAY_NAME_COOKIE, ''),
        'share_url': share_url_for_link(link, request=request),
        'share_title': f'{link.client.dog_name} at Dad4dogs',
        'comments_open': request.GET.get('comments') in ('1', 'true'),
        'download_url': download_url,
        'download_filename': download_filename,
    })
    return context


@require_GET
def public_feed_share(request, share_token: str):
    """Public moment page — photo, reactions, comments, re-share."""
    link = _resolve_share_link(share_token)
    if request.GET.get('posted') != '1':
        record_share_view(link)
    visitor_id = get_or_set_visitor_id(request)
    response = render(request, 'operations/public_photo_share.html', _share_page_context(request, link, visitor_id))
    get_or_set_visitor_id(request, response)
    return response


@require_POST
def public_feed_share_react(request, share_token: str):
    link = _resolve_share_link(share_token)
    visitor_id = get_or_set_visitor_id(request)
    emoji = (request.POST.get('emoji') or '').strip()
    try:
        set_reaction(client=link.client, asset_id=link.media_asset_id, visitor_id=visitor_id, emoji=emoji)
    except FeedInteractionError:
        pass
    return _redirect_share(share_token)


@require_POST
def public_feed_share_comment(request, share_token: str):
    link = _resolve_share_link(share_token)
    visitor_id = get_or_set_visitor_id(request)
    display_name = (request.POST.get('display_name') or '').strip()
    text = request.POST.get('text', '')
    try:
        add_comment(client=link.client, asset_id=link.media_asset_id, visitor_id=visitor_id, text=text, display_name=display_name)
    except FeedInteractionError:
        return _redirect_share(share_token, open_comments=True)

    response = _redirect_share(share_token, open_comments=True)
    set_display_name_cookie(response, request, display_name)
    return response


@require_GET
def public_feed_share_download(request, share_token: str):
    """Serve high-res media with dad4dogs_<uuid> filename."""
    link = _resolve_share_link(share_token)
    field, _ = share_download_field(link.media_asset)
    if not field or not getattr(field, 'name', ''):
        raise Http404('No downloadable media for this moment.')
    filename = share_download_filename(link, link.media_asset)
    return FileResponse(field.open('rb'), as_attachment=True, filename=filename)


@require_GET
def public_shared_media_legacy(request, share_id):
    """Redirect old /share/photo/<uuid>/ links to /feed/share/<token>/."""
    link = get_object_or_404(SharedMediaLink, pk=share_id)
    if not link.share_token:
        link.share_token = generate_unique_share_token()
        link.save(update_fields=['share_token'])
    return redirect('operations:public_feed_share', share_token=link.share_token)