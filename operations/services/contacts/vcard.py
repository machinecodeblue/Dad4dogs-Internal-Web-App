from operations.models import ClientProfile, CustomerOwner
from operations.services.addresses import format_unit
from operations.services.phones import e164


def _vcard_escape(value: str) -> str:
    return (
        (value or '')
        .replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\n', '\\n')
    )


def build_vcard(client: ClientProfile) -> str:
    """Build a vCard 3.0 file for export into Google Contacts."""
    name_parts = client.owner_name.split(None, 1)
    first = name_parts[0] if name_parts else client.owner_name
    last = name_parts[1] if len(name_parts) > 1 else ''

    lines = [
        'BEGIN:VCARD',
        'VERSION:3.0',
        f'N:{last};{first};;;',
        f'FN:{client.owner_name}',
        'ORG:Dad4dogs Client',
        f'TITLE:Dog: {client.dog_name}',
    ]
    if client.owner_email:
        lines.append(f'EMAIL;TYPE=INTERNET:{client.owner_email}')
    if client.owner_phone:
        lines.append(f'TEL;TYPE=CELL:{e164(client.owner_phone)}')

    owner = CustomerOwner.objects.filter(owner_email__iexact=client.owner_email).first()
    if owner and (owner.address_street or owner.address_postal_code or owner.formatted_address):
        if owner.address_street or owner.address_city or owner.address_postal_code:
            lines.append(
                'ADR;TYPE=HOME:'
                f';{_vcard_escape(format_unit(owner.address_unit))}'
                f';{_vcard_escape(owner.address_street)}'
                f';{_vcard_escape(owner.address_city)}'
                f';{_vcard_escape(owner.address_province)}'
                f';{_vcard_escape(owner.address_postal_code)}'
                ';Canada'
            )
        else:
            lines.append(f'ADR;TYPE=HOME:;;{_vcard_escape(owner.address_oneline)};;;;')

    note = client.notes.replace('\n', '\\n') if client.notes else ''
    lines.append(f'NOTE:Dog: {client.dog_name}. {note}'.rstrip('. '))
    lines.append('END:VCARD')
    return '\r\n'.join(lines) + '\r\n'