import uuid
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageOps


def unique_name(prefix: str, suffix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex}{suffix}'


def master_image_bytes(uploaded_file) -> tuple[bytes, str]:
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


def thumbnail_webp_bytes(master_bytes: bytes) -> bytes:
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
