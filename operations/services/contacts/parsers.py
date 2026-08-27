import csv
import io
from operations.services.phones import normalize_phone
from .schemas import ParsedContact


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _split_phones(raw: str) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(':::') if p.strip()]


def _split_emails(row: dict) -> list[str]:
    emails = []
    for key in ('E-mail 1 - Value', 'E-mail 2 - Value'):
        value = (row.get(key) or '').strip()
        if value:
            emails.append(value)
    return emails


def parse_google_csv(file_content: str | bytes) -> tuple[list[ParsedContact], int]:
    """Parse a Google Contacts CSV export into structured contact rows."""
    if isinstance(file_content, bytes):
        file_content = file_content.decode('utf-8-sig')

    reader = csv.DictReader(io.StringIO(file_content))
    contacts = []
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        emails = _split_emails(row)
        phones = _split_phones((row.get('Phone 1 - Value') or '').strip())
        first = (row.get('First Name') or '').strip()
        middle = (row.get('Middle Name') or '').strip()
        last = (row.get('Last Name') or '').strip()

        if not first and not emails and not phones:
            skipped += 1
            continue

        contact = ParsedContact(
            row_number=row_num,
            first_name=first,
            middle_name=middle,
            last_name=last,
            emails=emails,
            phones=phones,
            notes=(row.get('Notes') or '').strip(),
            primary_email=emails[0] if emails else '',
            primary_phone=phones[0] if phones else '',
            normalized_emails=[normalize_email(e) for e in emails if e],
            normalized_phones=[normalize_phone(p) for p in phones if p],
            display_name=' '.join(p for p in [first, middle, last] if p).strip(),
        )
        contacts.append(contact)

    return contacts, skipped