"""
Catalog-aware fee evaluation.

Phase 2: Visit.check_out uses this when business_service is set.
Classic DOG boarding reproduces operations.pricing overnight-first logic (parity).
Non-DOG / simple FLAT offerings charge the service base_rate for the stay window.
"""

from datetime import datetime
from decimal import Decimal

from operations.pricing import calculate_fee as legacy_calculate_fee


def calculate_service_fee(service, arrival: datetime, departure: datetime):
    """
    Return (Decimal total, list breakdown_lines) for a catalog service.

    breakdown items stay JSON-safe (string amounts), matching Visit.fee_breakdown.
    """
    if service is None:
        return legacy_calculate_fee(arrival, departure)

    # Classic dog boarding: keep overnight-first parity with pricing.py.
    if (
        service.target_category == service.TargetCategory.DOG
        and not service.capacity_exempt
    ):
        fee, breakdown = legacy_calculate_fee(arrival, departure)
        annotated = [
            {
                'tier': f'{service.name} — {item.get("tier", "Fee")}',
                'amount': item['amount'],
                'service_slug': service.slug,
            }
            for item in breakdown
        ]
        return fee, annotated

    # Property / small-pet / capacity-exempt: flat catalog rate for the stay.
    total = Decimal(str(service.base_rate))
    return total, [{
        'tier': service.name,
        'amount': str(total),
        'service_slug': service.slug,
    }]
