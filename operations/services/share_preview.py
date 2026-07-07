import os

from django.http import HttpRequest

from operations.models import SharedMediaLink, TimelineMediaAsset


def absolute_media_url(request: HttpRequest, file_field) -> str:
    if not file_field or not getattr(file_field, 'name', ''):
        return ''
    url = file_field.url
    if url.startswith('http'):
        return url
    return request.build_absolute_uri(url)


def share_preview_image_url(request: HttpRequest, asset: TimelineMediaAsset) -> str:
    """Best image for Open Graph / WhatsApp / Facebook link previews."""
    if asset.media_type == TimelineMediaAsset.MediaType.PHOTO:
        if asset.photo_high_res:
            return absolute_media_url(request, asset.photo_high_res)
        if asset.photo_thumbnail:
            return absolute_media_url(request, asset.photo_thumbnail)
    if asset.photo_thumbnail:
        return absolute_media_url(request, asset.photo_thumbnail)
    return ''


def share_download_field(asset: TimelineMediaAsset):
    """Best on-disk file to offer for visitor download."""
    if asset.media_type == TimelineMediaAsset.MediaType.PHOTO and asset.photo_high_res:
        return asset.photo_high_res, '.jpg'
    if asset.media_type == TimelineMediaAsset.MediaType.VIDEO and asset.video_file:
        return asset.video_file, '.mp4'
    if asset.photo_thumbnail:
        return asset.photo_thumbnail, '.jpg'
    return None, ''


def share_download_filename(link: SharedMediaLink, asset: TimelineMediaAsset) -> str:
    field, default_ext = share_download_field(asset)
    if not field or not getattr(field, 'name', ''):
        return ''
    ext = os.path.splitext(field.name)[1] or default_ext
    return f'dad4dogs_{link.id}{ext}'


def share_download_page_url(request: HttpRequest, link: SharedMediaLink) -> tuple[str, str]:
    """Return (download_endpoint_url, attachment_filename)."""
    filename = share_download_filename(link, link.media_asset)
    if not filename:
        return '', ''
    from django.urls import reverse

    path = reverse(
        'operations:public_feed_share_download',
        kwargs={'share_token': link.share_token},
    )
    return request.build_absolute_uri(path), filename


def build_share_preview_context(request: HttpRequest, link: SharedMediaLink) -> dict:
    asset = link.media_asset
    dog_name = link.client.dog_name
    canonical_url = request.build_absolute_uri(request.path)
    og_image = share_preview_image_url(request, asset)
    title = f'{dog_name} at Dad4dogs'
    description = f'A moment with {dog_name} — Dad4dogs'
    if asset.caption_notes.strip():
        description = asset.caption_notes.strip()[:200]

    return {
        'link': link,
        'photo': asset,
        'dog_name': dog_name,
        'og_title': title,
        'og_description': description,
        'og_image': og_image,
        'og_url': canonical_url,
        'og_type': 'article',
    }