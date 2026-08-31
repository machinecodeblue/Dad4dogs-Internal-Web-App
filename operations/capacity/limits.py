from datetime import date
from operations.models.business import (
    DEFAULT_INSURANCE_CEILING,
    DEFAULT_STANDARD_CAPACITY,
)

STANDARD_CAPACITY = DEFAULT_STANDARD_CAPACITY
WARNING_THRESHOLD = DEFAULT_STANDARD_CAPACITY + 1
INSURANCE_CEILING = DEFAULT_INSURANCE_CEILING


def capacity_limits() -> tuple[int, int]:
    """Standard daily capacity and insurance ceiling from CapacitySettings, else defaults."""
    from operations.models import CapacitySettings
    from operations.services.context_tenant import (
        ACTIVE_WORKSPACE_SLUG,
        get_active_workspace,
    )

    row = (
        CapacitySettings.objects.filter(workspace__slug=ACTIVE_WORKSPACE_SLUG)
        .values_list('standard_capacity', 'insurance_ceiling')
        .first()
    )
    if not row:
        get_active_workspace()
        row = (
            CapacitySettings.objects.filter(workspace__slug=ACTIVE_WORKSPACE_SLUG)
            .values_list('standard_capacity', 'insurance_ceiling')
            .first()
        )
    if not row:
        return STANDARD_CAPACITY, INSURANCE_CEILING
    standard, ceiling = row
    if not standard or standard < 1:
        standard = STANDARD_CAPACITY
    if not ceiling or ceiling < 1:
        ceiling = INSURANCE_CEILING
    if ceiling < standard:
        ceiling = standard
    return standard, ceiling


def format_capacity_status(
    count: int,
    day: date,
    *,
    standard: int | None = None,
    ceiling: int | None = None,
) -> dict:
    if standard is None or ceiling is None:
        standard, ceiling = capacity_limits()
    base = {
        'count': count,
        'standard': standard,
        'ceiling': ceiling,
    }
    if count > ceiling:
        return {
            **base,
            'status': 'blocked',
            'message': (
                f'Insurance ceiling reached: {count} dogs scheduled on {day}. '
                f'Maximum {ceiling} dogs allowed.'
            ),
        }
    if count > standard:
        return {
            **base,
            'status': 'warning',
            'message': (
                f'Capacity warning: {count} dogs on {day}. '
                f'Standard capacity is {standard}; insurance allows up to {ceiling}.'
            ),
        }
    return {
        **base,
        'status': 'ok',
        'message': f'{count} of {standard} standard capacity used on {day}.',
    }