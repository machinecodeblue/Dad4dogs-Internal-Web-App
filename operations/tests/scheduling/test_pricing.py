from datetime import datetime
from decimal import Decimal

from django.test import TestCase

from operations.pricing import calculate_fee, is_overnight_segment
from operations.tests.conftest import TZ


class PricingEngineTests(TestCase):
    def test_short_visit(self):
        start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('15.00'))
        self.assertEqual(items[0]['tier'], 'Short Visit')

    def test_daytime_visit(self):
        start = datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 18, 0, tzinfo=TZ)
        fee, _ = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('25.00'))

    def test_overnight_priority_over_daytime_hours(self):
        """1 PM to 1 AM (12h) must be Overnight, not Daytime."""
        start = datetime(2026, 3, 10, 13, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 1, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('37.50'))
        self.assertEqual(items[0]['tier'], 'Overnight')
        self.assertTrue(is_overnight_segment(start, end))

    def test_multiday_24h_plus_3h(self):
        start = datetime(2026, 3, 10, 13, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 16, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('52.50'))
        tiers = [i['tier'] for i in items]
        self.assertIn('Overnight (24h block)', tiers)
        self.assertIn('Short Visit', tiers)

    def test_multiday_24h_plus_11h(self):
        start = datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
        end = datetime(2026, 3, 11, 19, 0, tzinfo=TZ)
        fee, items = calculate_fee(start, end)
        self.assertEqual(fee, Decimal('62.50'))
        tiers = [i['tier'] for i in items]
        self.assertIn('Overnight (24h block)', tiers)
        self.assertIn('Daytime Visit', tiers)

    def test_line_items_are_json_serializable(self):
        start = datetime(2026, 3, 10, 9, 0, tzinfo=TZ)
        end = datetime(2026, 3, 10, 12, 0, tzinfo=TZ)
        _, items = calculate_fee(start, end)
        self.assertEqual(items[0]['amount'], '15.00')
        self.assertIsInstance(items[0]['amount'], str)