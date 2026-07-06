from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from operations.models import AccountStatement, Visit


def week_bounds(reference: date | None = None) -> tuple[date, date]:
    ref = reference or timezone.localdate()
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


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
    ).select_related('client')

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
            line_items.append({
                'visit_id': visit.pk,
                'date': visit.actual_departure.strftime('%Y-%m-%d'),
                'arrival': (visit.actual_arrival or visit.scheduled_start).isoformat(),
                'departure': visit.actual_departure.isoformat(),
                'fee': str(fee),
                'breakdown': visit.fee_breakdown,
            })

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


def format_statement_email(statement: AccountStatement) -> str:
    client = statement.client
    lines = [
        f'Statement of Account — Dad4dogs',
        f'Week of {statement.week_start} to {statement.week_end}',
        f'',
        f'Client: {client.owner_name}',
        f'Dog: {client.dog_name}',
        f'Email: {client.owner_email}',
        f'',
        f'Visits:',
    ]
    for item in statement.line_items:
        lines.append(f"  {item['date']}: ${item['fee']} CAD")
    lines.extend([
        f'',
        f'Total Due: ${statement.total_amount} CAD',
        f'',
        f'Please send payment via e-Transfer.',
        f'',
        f'Thank you,',
        f'David — Dad4dogs',
    ])
    return '\n'.join(lines)