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