from datetime import datetime, time, timedelta
from decimal import Decimal

SHORT_RATE = Decimal('15.00')
DAY_RATE = Decimal('25.00')
OVERNIGHT_RATE = Decimal('37.50')


def _line_item(tier: str, amount: Decimal) -> dict:
    """Build a JSONField-safe fee line item (Decimal amounts are not JSON-serializable)."""
    return {'tier': tier, 'amount': str(amount)}


def is_overnight_segment(start: datetime, end: datetime) -> bool:
    """True if stay begins before 4:00 AM or crosses the 11 PM–4 AM window."""
    if start >= end:
        return False
    if start.hour < 4:
        return True

    day = start.date()
    end_day = end.date()
    tz = start.tzinfo
    while day <= end_day:
        eleven_pm = datetime.combine(day, time(23, 0), tzinfo=tz)
        four_am = datetime.combine(day + timedelta(days=1), time(4, 0), tzinfo=tz)
        if start < four_am and end > eleven_pm:
            return True
        day += timedelta(days=1)
    return False


def _tier_remainder(start: datetime, end: datetime) -> tuple[Decimal, list[dict]]:
    """Price a segment shorter than 24 hours."""
    duration = end - start
    hours = duration.total_seconds() / 3600

    if is_overnight_segment(start, end):
        return OVERNIGHT_RATE, [_line_item('Overnight', OVERNIGHT_RATE)]

    if hours <= 4:
        return SHORT_RATE, [_line_item('Short Visit', SHORT_RATE)]
    if hours <= 12:
        return DAY_RATE, [_line_item('Daytime Visit', DAY_RATE)]

    # Remainder exceeds 12 hours without overnight boundary — treat as another 24h block.
    block_end = start + timedelta(days=1)
    block_fee, block_items = OVERNIGHT_RATE, [_line_item('Overnight (24h block)', OVERNIGHT_RATE)]
    if block_end < end:
        rest_fee, rest_items = _tier_remainder(block_end, end)
        return block_fee + rest_fee, block_items + rest_items
    return block_fee, block_items


def calculate_fee(arrival: datetime, departure: datetime) -> tuple[Decimal, list[dict]]:
    """
    Calculate stay fee using overnight-first logic and multi-day accumulation.

    Each full 24-hour block is charged as Overnight ($37.50).
    The remainder is priced with overnight boundary checked before hour tiers.
    """
    if arrival >= departure:
        return Decimal('0.00'), []

    total = Decimal('0.00')
    line_items: list[dict] = []
    duration = departure - arrival
    full_blocks = int(duration.total_seconds() // (24 * 3600))

    for _ in range(full_blocks):
        total += OVERNIGHT_RATE
        line_items.append(_line_item('Overnight (24h block)', OVERNIGHT_RATE))

    remainder_start = arrival + timedelta(days=full_blocks)
    if remainder_start < departure:
        remainder_fee, remainder_items = _tier_remainder(remainder_start, departure)
        total += remainder_fee
        line_items.extend(remainder_items)

    return total, line_items