import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps

from operations.models import TimelineMediaAsset, Visit, VisitTimelineEvent
from operations.services.timeline_visits import active_checked_in_visits


class TimelineMediaError(Exception):
    """Raised when timeline media cannot be processed."""


def _unique_name(prefix: str, suffix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex}{suffix}'


def _master_image_bytes(uploaded_file) -> tuple[bytes, str]:
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)

    if image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
        ext = '.jpg'
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=95, optimize=True)
        return buffer.getvalue(), ext

    fmt = (image.format or 'JPEG').upper()
    if fmt in ('JPEG', 'JPG'):
        ext = '.jpg'
        save_format = 'JPEG'
    elif fmt == 'PNG':
        ext = '.png'
        save_format = 'PNG'
    else:
        ext = '.jpg'
        save_format = 'JPEG'
        image = image.convert('RGB')

    buffer = BytesIO()
    if save_format == 'JPEG':
        image.save(buffer, format=save_format, quality=95, optimize=True)
    else:
        image.save(buffer, format=save_format)
    return buffer.getvalue(), ext


def _thumbnail_webp_bytes(master_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(master_bytes))
    image = ImageOps.exif_transpose(image)
    image.thumbnail(
        (settings.TIMELINE_THUMBNAIL_MAX_PX, settings.TIMELINE_THUMBNAIL_MAX_PX),
        Image.Resampling.LANCZOS,
    )
    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGB')
    buffer = BytesIO()
    image.save(buffer, format='WEBP', quality=80, method=6)
    return buffer.getvalue()


def _validate_checked_in_visits(visit_ids: list[int]) -> list[Visit]:
    if not visit_ids:
        raise TimelineMediaError('Select at least one checked-in dog.')

    allowed_ids = set(active_checked_in_visits().values_list('pk', flat=True))
    invalid = set(visit_ids) - allowed_ids
    if invalid:
        raise TimelineMediaError('One or more selected dogs are not currently checked in.')

    visits = list(
        Visit.objects.filter(pk__in=visit_ids).select_related('client').order_by('client__dog_name'),
    )
    if len(visits) != len(set(visit_ids)):
        raise TimelineMediaError('Invalid visit selection.')
    return visits


def attach_asset_to_visits(
    *,
    asset: TimelineMediaAsset,
    visits: list[Visit],
    source_event: VisitTimelineEvent | None = None,
) -> list[VisitTimelineEvent]:
    created = []
    for visit in visits:
        if VisitTimelineEvent.objects.filter(visit=visit, media_asset=asset).exists():
            continue
        if not visit.accepts_timeline_events:
            raise TimelineMediaError(
                f'{visit.client.dog_name} is no longer checked in.',
            )
        created.append(
            VisitTimelineEvent.objects.create(
                visit=visit,
                media_asset=asset,
                source_event=source_event,
            ),
        )
    if not created:
        raise TimelineMediaError('This moment is already on the selected timelines.')
    return created


def create_photo_asset(
    *,
    uploaded_file,
    caption_notes: str,
    latitude,
    longitude,
    used_fallback: bool,
    fallback_label: str,
    original_visit: Visit,
) -> TimelineMediaAsset:
    if not uploaded_file:
        raise TimelineMediaError('Photo file is required.')

    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type and not content_type.startswith('image/'):
        raise TimelineMediaError('Only image uploads are allowed for photos.')

    try:
        master_bytes, ext = _master_image_bytes(uploaded_file)
        thumb_bytes = _thumbnail_webp_bytes(master_bytes)
    except Exception as exc:
        raise TimelineMediaError(f'Could not process image: {exc}') from exc

    asset = TimelineMediaAsset(
        media_type=TimelineMediaAsset.MediaType.PHOTO,
        caption_notes=caption_notes,
        latitude=latitude,
        longitude=longitude,
        location_used_fallback=used_fallback,
        location_fallback_label=fallback_label,
        captured_at=timezone.now(),
        original_visit=original_visit,
    )
    asset.photo_high_res.save(_unique_name('master', ext), ContentFile(master_bytes), save=False)
    asset.photo_thumbnail.save(_unique_name('thumb', '.webp'), ContentFile(thumb_bytes), save=False)
    asset.save()
    return asset


def create_video_asset(
    *,
    uploaded_file,
    caption_notes: str,
    latitude,
    longitude,
    used_fallback: bool,
    fallback_label: str,
    original_visit: Visit,
) -> TimelineMediaAsset:
    if not uploaded_file:
        raise TimelineMediaError('Video file is required.')

    if uploaded_file.size > settings.TIMELINE_VIDEO_MAX_BYTES:
        raise TimelineMediaError('Video must be 25 MB or smaller.')

    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type and not content_type.startswith('video/'):
        raise TimelineMediaError('Only video files are allowed for gallery upload.')

    original_name = getattr(uploaded_file, 'name', 'video.mp4') or 'video.mp4'
    suffix = '.' + original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else '.mp4'

    asset = TimelineMediaAsset(
        media_type=TimelineMediaAsset.MediaType.VIDEO,
        caption_notes=caption_notes,
        latitude=latitude,
        longitude=longitude,
        location_used_fallback=used_fallback,
        location_fallback_label=fallback_label,
        captured_at=timezone.now(),
        original_visit=original_visit,
    )
    asset.video_file.save(_unique_name('video', suffix), uploaded_file, save=False)
    asset.save()
    return asset


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
    visits = _validate_checked_in_visits(target_visit_ids)
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