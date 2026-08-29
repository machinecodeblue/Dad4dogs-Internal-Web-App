from decimal import Decimal

from operations.models import AccountStatement, Visit


def _billed_visit_ids(client_id: int | None = None) -> set[int]:
    qs = AccountStatement.objects.all()
    if client_id is not None:
        qs = qs.filter(client_id=client_id)
    billed_ids: set[int] = set()
    for items in qs.values_list('line_items', flat=True):
        for item in items or []:
            visit_id = item.get('visit_id')
            if visit_id is not None:
                billed_ids.add(int(visit_id))
    return billed_ids


def _summary_for_visits(qs) -> dict:
    count = 0
    total = Decimal('0.00')
    for fee in qs.values_list('calculated_fee', flat=True):
        count += 1
        if fee is not None:
            total += fee
    return {'count': count, 'total': total}


def get_unbilled_summary_for_client(client_id: int) -> dict:
    """
    Completed visits for this dog whose visit_id is not on any statement line item.

    Returns {"count": int, "total": Decimal}.
    """
    if not client_id:
        return {'count': 0, 'total': Decimal('0.00')}

    billed_ids = _billed_visit_ids(client_id)
    qs = Visit.objects.filter(
        client_id=client_id,
        status=Visit.Status.COMPLETED,
    ).exclude(pk__in=billed_ids)
    return _summary_for_visits(qs)


def get_workspace_unbilled_summary() -> dict:
    """Completed visits not present on any statement line item (workspace-wide)."""
    billed_ids = _billed_visit_ids()
    qs = Visit.objects.filter(status=Visit.Status.COMPLETED).exclude(pk__in=billed_ids)
    return _summary_for_visits(qs)
