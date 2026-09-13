"""Active workspace business timezone helpers."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings

from operations.models.business import (
    BUSINESS_TIMEZONE_VALUES,
    DEFAULT_BUSINESS_TIMEZONE,
)


def get_business_timezone_name() -> str:
    """IANA timezone name for the active business (Settings), with safe fallback."""
    try:
        from operations.models import BusinessProfile

        name = (BusinessProfile.load().timezone or '').strip()
    except Exception:
        name = ''
    if name in BUSINESS_TIMEZONE_VALUES:
        return name
    fallback = (getattr(settings, 'TIME_ZONE', '') or '').strip()
    if fallback in BUSINESS_TIMEZONE_VALUES:
        return fallback
    return DEFAULT_BUSINESS_TIMEZONE


def get_business_timezone() -> ZoneInfo:
    name = get_business_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_BUSINESS_TIMEZONE)
