from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from operations.models import TimelineMediaAsset, Visit
from operations.services.timeline_media.errors import TimelineMediaError
from operations.services.timeline_media.imaging import (
    master_image_bytes,
    thumbnail_webp_bytes,
    unique_name,
)


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
        master_bytes, ext = master_image_bytes(uploaded_file)
        thumb_bytes = thumbnail_webp_bytes(master_bytes)
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
    asset.photo_high_res.save(unique_name('master', ext), ContentFile(master_bytes), save=False)
    asset.photo_thumbnail.save(unique_name('thumb', '.webp'), ContentFile(thumb_bytes), save=False)
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
    asset.video_file.save(unique_name('video', suffix), uploaded_file, save=False)
    asset.save()
    return asset
