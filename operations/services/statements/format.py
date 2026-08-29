from operations.models import AccountStatement, CustomerOwner


def statement_email_subject(statement: AccountStatement) -> str:
    dog = statement.client.dog_name
    return f'Dad4dogs statement — {dog} — week of {statement.week_start}'


def format_statement_email(statement: AccountStatement) -> str:
    client = statement.client
    owner = CustomerOwner.objects.filter(owner_email__iexact=client.owner_email).first()
    lines = [
        f'Statement of Account — Dad4dogs',
        f'Week of {statement.week_start} to {statement.week_end}',
        f'',
        f'Client: {client.owner_name}',
        f'Dog: {client.dog_name}',
        f'Email: {client.owner_email}',
    ]
    if owner and owner.address_oneline:
        lines.append(f'Address: {owner.address_oneline}')
    lines.extend([
        f'',
        f'Visits:',
    ])
    for item in statement.line_items:
        service = (item.get('service_name') or '').strip()
        if service:
            lines.append(f"  {item['date']}: {service} — ${item['fee']} CAD")
        else:
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
