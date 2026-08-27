from operations.models.customers import ClientProfile
from operations.models.scheduling import MediaReaction
from operations.services.feed_interactions.errors import FeedInteractionError
from operations.services.feed_interactions.queries import asset_belongs_to_client


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
