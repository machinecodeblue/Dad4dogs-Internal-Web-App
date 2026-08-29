from datetime import date, timedelta
from decimal import Decimal

from operations.models import AccountStatement, Visit

from .weeks import week_bounds


def generate_weekly_statements(week_start: date | None = None) -> list[AccountStatement]:
    """Compile completed visits into weekly statements per client."""
    if week_start is None:
        week_start, week_end = week_bounds()
    else:
        week_end = week_start + timedelta(days=6)

    visits = Visit.objects.filter(
        status=Visit.Status.COMPLETED,
        actual_departure__date__gte=week_start,
        actual_departure__date__lte=week_end,
    ).select_related('client', 'business_service')

    by_client: dict[int, list] = {}
    for visit in visits:
        by_client.setdefault(visit.client_id, []).append(visit)

    statements = []
    for client_id, client_visits in by_client.items():
        line_items = []
        total = Decimal('0.00')
        for visit in client_visits:
            fee = visit.calculated_fee or Decimal('0.00')
            total += fee
            item = {
                'visit_id': visit.pk,
                'date': visit.actual_departure.strftime('%Y-%m-%d'),
                'arrival': (visit.actual_arrival or visit.scheduled_start).isoformat(),
                'departure': visit.actual_departure.isoformat(),
                'fee': str(fee),
                'breakdown': visit.fee_breakdown,
            }
            service = visit.business_service
            if service is not None:
                item['service_name'] = service.name
                item['service_slug'] = service.slug
            line_items.append(item)

        statement, _ = AccountStatement.objects.update_or_create(
            client_id=client_id,
            week_start=week_start,
            defaults={
                'week_end': week_end,
                'line_items': line_items,
                'total_amount': total,
                'send_status': AccountStatement.SendStatus.QUEUED,
            },
        )
        statements.append(statement)

    return statements
