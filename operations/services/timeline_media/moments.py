from django.db import transaction

from operations.models import TimelineMediaAsset, Visit, VisitTimelineEvent
from operations.services.timeline_media.assets import create_photo_asset, create_video_asset
from operations.services.timeline_media.attach import (
    attach_asset_to_visits,
    validate_checked_in_visits,
)
from operations.services.timeline_media.errors import TimelineMediaError
from operations.services.timeline_visits import active_checked_in_visits


@transaction.atomic
def log_moment_for_visits(
    *,
    visits: list[Visit],
    media_kind: str,
    uploaded_file,
    caption_notes: str,
    latitude,
    longitude,
    used_fallback: bool,
    fallback_label: str,
) -> tuple[TimelineMediaAsset, list[VisitTimelineEvent]]:
    original_visit = visits[0]
    if media_kind == 'photo':
        asset = create_photo_asset(
            uploaded_file=uploaded_file,
            caption_notes=caption_notes,
            latitude=latitude,
            longitude=longitude,
            used_fallback=used_fallback,
            fallback_label=fallback_label,
            original_visit=original_visit,
        )
    else:
        asset = create_video_asset(
            uploaded_file=uploaded_file,
            caption_notes=caption_notes,
            latitude=latitude,
            longitude=longitude,
            used_fallback=used_fallback,
            fallback_label=fallback_label,
            original_visit=original_visit,
        )
    events = attach_asset_to_visits(asset=asset, visits=visits)
    return asset, events


def forward_timeline_event(
    *,
    source_event: VisitTimelineEvent,
    target_visit_ids: list[int],
) -> list[VisitTimelineEvent]:
    visits = validate_checked_in_visits(target_visit_ids)
    visits = [v for v in visits if v.pk != source_event.visit_id]
    if not visits:
        raise TimelineMediaError('Select at least one other checked-in dog.')
    return attach_asset_to_visits(
        asset=source_event.media_asset,
        visits=visits,
        source_event=source_event,
    )


def visits_available_for_forward(source_event: VisitTimelineEvent):
    asset = source_event.media_asset
    linked_visit_ids = VisitTimelineEvent.objects.filter(media_asset=asset).values_list(
        'visit_id', flat=True,
    )
    return active_checked_in_visits().exclude(pk__in=linked_visit_ids)
