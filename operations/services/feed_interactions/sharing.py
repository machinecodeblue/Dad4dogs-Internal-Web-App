from operations.models import ClientProfile, SharedMediaLink
from operations.services.feed_interactions.queries import asset_belongs_to_client
from operations.services.feed_slugs import generate_unique_share_token


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
