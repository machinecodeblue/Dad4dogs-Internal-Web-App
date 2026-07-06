from decimal import Decimal, InvalidOperation

from django.conf import settings

from operations.models import BusinessProfile


def _parse_coordinate(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        coord = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return coord


def resolve_timeline_coordinates(
    latitude,
    longitude,
) -> tuple[Decimal, Decimal, bool, str]:
    """
    Return (lat, lng, used_fallback, fallback_label).

    When device GPS is missing, apply the business site fallback coordinates
    and label from Business Settings.
    """
    lat = _parse_coordinate(latitude)
    lng = _parse_coordinate(longitude)

    if lat is not None and lng is not None:
        if Decimal('-90') <= lat <= Decimal('90') and Decimal('-180') <= lng <= Decimal('180'):
            return lat, lng, False, ''

    profile = BusinessProfile.load()
    fallback_label = profile.calendar_location or '191 Grey Street, London, Ontario'
    return (
        Decimal(str(settings.BUSINESS_FALLBACK_LATITUDE)),
        Decimal(str(settings.BUSINESS_FALLBACK_LONGITUDE)),
        True,
        fallback_label,
    )