from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from operations.models import BusinessProfile
from operations.services.business_timezone import (
    get_business_timezone,
    get_business_timezone_name,
)
from operations.services.datetime_parse import parse_datetime_text


class BusinessTimezoneHelpersTests(TestCase):
    def test_default_timezone_is_toronto(self):
        profile = BusinessProfile.load()
        self.assertEqual(profile.timezone, 'America/Toronto')
        self.assertEqual(get_business_timezone_name(), 'America/Toronto')
        self.assertEqual(get_business_timezone().key, 'America/Toronto')

    def test_parse_uses_activated_business_timezone(self):
        profile = BusinessProfile.load()
        profile.timezone = 'America/Edmonton'
        profile.save(update_fields=['timezone', 'updated_at'])

        timezone.activate(get_business_timezone())
        try:
            parsed = parse_datetime_text('September 13, 2026 11:00 AM')
        finally:
            timezone.deactivate()

        self.assertEqual(getattr(parsed.tzinfo, 'key', None), 'America/Edmonton')
        self.assertEqual(parsed.hour, 11)
        self.assertEqual(parsed.minute, 0)

    @override_settings(TIME_ZONE='America/Toronto')
    def test_helper_reads_saved_profile_timezone(self):
        profile = BusinessProfile.load()
        profile.timezone = 'America/Vancouver'
        profile.save(update_fields=['timezone', 'updated_at'])
        self.assertEqual(get_business_timezone_name(), 'America/Vancouver')
        self.assertEqual(get_business_timezone(), ZoneInfo('America/Vancouver'))
