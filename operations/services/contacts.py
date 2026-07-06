import csv
import io
import re
from dataclasses import dataclass, field

from operations.models import ClientProfile, CustomerOwner

GOOGLE_CSV_FIELDS = [
    'First Name', 'Middle Name', 'Last Name',
    'E-mail 1 - Value', 'E-mail 2 - Value',
    'Phone 1 - Value', 'Notes',
]


@dataclass
class ParsedContact:
    row_number: int
    first_name: str = ''
    middle_name: str = ''
    last_name: str = ''
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    notes: str = ''
    primary_email: str = ''
    primary_phone: str = ''
    normalized_emails: list[str] = field(default_factory=list)
    normalized_phones: list[str] = field(default_factory=list)
    display_name: str = ''

    def __post_init__(self):
        self.normalized_emails = [normalize_email(e) for e in self.emails if e]
        self.normalized_phones = [normalize_phone(p) for p in self.phones if p]
        self.primary_email = self.emails[0] if self.emails else ''
        self.primary_phone = self.phones[0] if self.phones else ''
        parts = [self.first_name, self.middle_name, self.last_name]
        self.display_name = ' '.join(p for p in parts if p).strip()


@dataclass
class DuplicateGroup:
    match_type: str
    match_value: str
    contacts: list[ParsedContact] = field(default_factory=list)
    existing_clients: list[ClientProfile] = field(default_factory=list)
    existing_owners: list[CustomerOwner] = field(default_factory=list)
    source: str = ''


@dataclass
class ImportAnalysis:
    contacts: list[ParsedContact]
    csv_email_duplicates: list[DuplicateGroup]
    csv_phone_duplicates: list[DuplicateGroup]
    db_email_matches: list[DuplicateGroup]
    db_phone_matches: list[DuplicateGroup]
    new_contacts: list[ParsedContact]
    selectable_contacts: list[dict]
    name_review_contacts: list[dict]
    total_rows: int
    skipped_rows: int
    name_issues_count: int = 0


DOG_NICKNAME_KEYWORDS = {
    'contact', 'dog', 'mix', 'doodle', 'golden', 'sheep', 'spaniel', 'husky',
    'shepard', 'shepherd', 'babe', 'mommy', 'milkie', 'milky', 'guy', 'lady',
    'hunger', 'mac', 'brasil', 'stratford', 'port', 'elgin', 'berma', 'skipper',
    'bruiser', 'simba', 'peanut', 'nunez', 'deng', 'poodle', 'labrador',
}

INFORMAL_ONLY_NAMES = {
    'andi', 'bagan', 'brian', 'casey', 'cyril', 'dante', 'dean', 'emma', 'grace',
    'jacsa', 'jeff', 'jennifer', 'josna', 'ligi', 'lindsay', 'lisa', 'lloyd',
    'lori', 'maggie', 'mark', 'mary', 'melody', 'micheal', 'mike', 'omar', 'pask',
    'paulina', 'rebeca', 'runi', 'sanya', 'sonia', 'terry', 'tory', 'cynthia',
    'cassidy', 'emmalee', 'olivia', 'priyan', 'shervinso', 'krishna', 'evan',
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def is_valid_dog_name(dog_name: str, owner_name: str) -> bool:
    """A dog record is only created when we have a real dog name."""
    if not dog_name or dog_name.strip().upper() in ('TBD', 'UNKNOWN'):
        return False
    owner_first = owner_name.split()[0].lower() if owner_name else ''
    return bool(dog_name.strip()) and dog_name.strip().lower() != owner_first


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

        if not first and not emails and not phones:
            skipped += 1
            continue

        contacts.append(ParsedContact(
            row_number=row_num,
            first_name=first,
            middle_name=(row.get('Middle Name') or '').strip(),
            last_name=(row.get('Last Name') or '').strip(),
            emails=emails,
            phones=phones,
            notes=(row.get('Notes') or '').strip(),
        ))

    return contacts, skipped


def _extract_dog_from_notes(notes: str) -> str:
    match = re.search(r"dog'?s name is ([^.,\n;]+)", notes, re.IGNORECASE)
    return match.group(1).strip() if match else ''


def _first_looks_like_dog_nickname(first_name: str) -> bool:
    lower = first_name.lower()
    words = set(re.split(r'[\s\-]+', lower))
    if words & DOG_NICKNAME_KEYWORDS:
        return True
    if any(kw in lower for kw in DOG_NICKNAME_KEYWORDS):
        return True
    if lower.endswith(' contact'):
        return True
    return False


def assess_name_quality(contact: ParsedContact) -> list[str]:
    """Return human-readable flags when Google name fields look unreliable."""
    issues = []

    if not contact.first_name and not contact.last_name:
        issues.append('No name recorded')
        return issues

    if contact.first_name and not contact.last_name:
        issues.append('Missing last name — confirm owner\'s full name')

    if _first_looks_like_dog_nickname(contact.first_name):
        issues.append('First name looks like a dog nickname, not an owner')

    if contact.first_name and len(contact.first_name.split()) >= 3:
        issues.append('First name has multiple words — may be a description')

    if contact.first_name.lower() in INFORMAL_ONLY_NAMES and not contact.last_name:
        issues.append('Only a first name on file — get full name when you speak')

    dog_in_notes = _extract_dog_from_notes(contact.notes)
    if dog_in_notes and dog_in_notes.lower() != contact.first_name.lower():
        issues.append(f'Notes say dog is "{dog_in_notes}" — names may be swapped')

    if contact.middle_name and contact.middle_name.lower() in {'golden', 'doodle', 'labrador', 'retriever'}:
        issues.append('Breed appears in name fields — dog vs owner unclear')

    if contact.first_name and contact.last_name and not _first_looks_like_dog_nickname(contact.first_name):
        if not dog_in_notes:
            issues.append(
                f'"{contact.first_name} {contact.last_name}" looks like the owner — add a dog separately',
            )

    if not issues and contact.first_name and contact.last_name:
        if contact.first_name.islower() or contact.last_name.islower():
            issues.append('Name not properly capitalized — verify spelling')

    return issues


def suggest_client_fields(contact: ParsedContact) -> dict:
    """Best-guess mapping from Google contact fields to customer + optional dog."""
    dog_in_notes = _extract_dog_from_notes(contact.notes)
    first = contact.first_name
    last = contact.last_name
    middle = contact.middle_name

    if dog_in_notes:
        dog_name = dog_in_notes
        owner_parts = [p for p in [first, middle, last] if p]
        owner_name = ' '.join(owner_parts) if owner_parts else contact.display_name
    elif _first_looks_like_dog_nickname(first) and last:
        dog_name = first
        owner_name = last if not middle else f'{middle} {last}'.strip()
    elif first and last and not _first_looks_like_dog_nickname(first):
        dog_name = ''
        owner_parts = [p for p in [first, middle, last] if p]
        owner_name = ' '.join(owner_parts)
    elif first and last:
        dog_name = first
        owner_name = f'{middle} {last}'.strip() if middle else last
    elif first:
        dog_name = ''
        owner_name = first
    else:
        dog_name = ''
        owner_name = contact.display_name or 'Unknown'

    return {
        'dog_name': dog_name[:100] if dog_name else '',
        'owner_name': owner_name[:200],
        'owner_email': contact.primary_email,
        'owner_phone': contact.primary_phone[:30] if contact.primary_phone else '',
        'notes': contact.notes,
        'has_dog': is_valid_dog_name(dog_name, owner_name),
    }


def _group_by_field(
    contacts: list[ParsedContact],
    field: str,
    match_type: str,
    source: str,
) -> list[DuplicateGroup]:
    buckets: dict[str, list[ParsedContact]] = {}
    getter = (lambda c: c.normalized_emails) if field == 'email' else (lambda c: c.normalized_phones)

    for contact in contacts:
        for value in getter(contact):
            if not value:
                continue
            buckets.setdefault(value, []).append(contact)

    groups = []
    for value, members in buckets.items():
        unique_rows = {c.row_number for c in members}
        if len(unique_rows) > 1:
            groups.append(DuplicateGroup(
                match_type=match_type,
                match_value=value,
                contacts=members,
                source=source,
            ))
    return sorted(groups, key=lambda g: g.match_value)


def _match_against_db(
    contacts: list[ParsedContact],
    field: str,
    match_type: str,
) -> list[DuplicateGroup]:
    groups = []
    seen: set[tuple[str, int]] = set()

    if field == 'email':
        db_index: dict[str, list[ClientProfile]] = {}
        for client in ClientProfile.objects.all():
            key = normalize_email(client.owner_email)
            db_index.setdefault(key, []).append(client)
        owner_index = {
            normalize_email(o.owner_email): o
            for o in CustomerOwner.objects.all()
        }
    else:
        db_index = {}
        owner_index = {}
        for client in ClientProfile.objects.exclude(owner_phone=''):
            key = normalize_phone(client.owner_phone)
            if key:
                db_index.setdefault(key, []).append(client)

    for contact in contacts:
        values = contact.normalized_emails if field == 'email' else contact.normalized_phones
        for value in values:
            if not value:
                continue
            if field == 'email':
                if value not in db_index and value not in owner_index:
                    continue
                clients = db_index.get(value, [])
            else:
                if value not in db_index:
                    continue
                clients = db_index[value]

            if not clients:
                owner = owner_index.get(value) if field == 'email' else None
                dedupe_key = (value, owner.pk if owner else 0)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                groups.append(DuplicateGroup(
                    match_type=match_type,
                    match_value=value,
                    contacts=[contact],
                    existing_clients=[],
                    existing_owners=[owner] if owner else [],
                    source='database',
                ))
                continue

            for client in clients:
                dedupe_key = (value, client.pk)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                groups.append(DuplicateGroup(
                    match_type=match_type,
                    match_value=value,
                    contacts=[contact],
                    existing_clients=[client],
                    source='database',
                ))

    return sorted(groups, key=lambda g: (g.match_value, g.contacts[0].row_number))


def _rows_in_csv_duplicate_groups(groups: list[DuplicateGroup]) -> set[int]:
    rows = set()
    for group in groups:
        for contact in group.contacts:
            rows.add(contact.row_number)
    return rows


def _rows_matched_in_db(groups: list[DuplicateGroup]) -> set[int]:
    return _rows_in_csv_duplicate_groups(groups)


def _is_new_contact(contact: ParsedContact, email_matches: list[DuplicateGroup], phone_matches: list[DuplicateGroup]) -> bool:
    matched_rows = set()
    for group in email_matches + phone_matches:
        for c in group.contacts:
            matched_rows.add(c.row_number)
    return contact.row_number not in matched_rows


def _contact_import_status(
    contact: ParsedContact,
    csv_dup_rows: set[int],
    db_matched_rows: set[int],
    suggested: dict,
) -> tuple[str, bool]:
    email = suggested.get('owner_email', '')
    if email and CustomerOwner.objects.filter(owner_email__iexact=email).exists():
        if suggested.get('has_dog'):
            return 'in_db', False
        return 'customer_exists', False
    if contact.row_number in db_matched_rows:
        return 'in_db', False
    if contact.row_number in csv_dup_rows:
        return 'csv_duplicate', True
    return 'new', True


def analyze_import(contacts: list[ParsedContact], skipped: int = 0) -> ImportAnalysis:
    """Compare parsed Google contacts against each other and the existing database."""
    csv_email_dups = _group_by_field(contacts, 'email', 'email', 'csv')
    csv_phone_dups = _group_by_field(contacts, 'phone', 'phone', 'csv')
    db_email_matches = _match_against_db(contacts, 'email', 'email')
    db_phone_matches = _match_against_db(contacts, 'phone', 'phone')

    new_contacts = [
        c for c in contacts
        if _is_new_contact(c, db_email_matches, db_phone_matches)
        and not any(c.row_number in {x.row_number for x in g.contacts} for g in csv_email_dups + csv_phone_dups)
    ]

    csv_dup_rows = _rows_in_csv_duplicate_groups(csv_email_dups + csv_phone_dups)
    db_matched_rows = _rows_matched_in_db(db_email_matches + db_phone_matches)

    selectable_contacts = []
    name_review_contacts = []
    name_issues_count = 0

    for contact in contacts:
        name_issues = assess_name_quality(contact)
        suggested = suggest_client_fields(contact)
        import_status, can_import = _contact_import_status(
            contact, csv_dup_rows, db_matched_rows, suggested,
        )

        if not suggested['owner_email']:
            can_import = False
            import_status = 'no_email'

        entry = {
            'row_number': contact.row_number,
            'display_name': contact.display_name,
            'first_name': contact.first_name,
            'middle_name': contact.middle_name,
            'last_name': contact.last_name,
            'emails': contact.emails,
            'phones': contact.phones,
            'notes': contact.notes[:300],
            'name_issues': name_issues,
            'needs_name_review': bool(name_issues),
            'suggested_dog_name': suggested['dog_name'],
            'suggested_owner_name': suggested['owner_name'],
            'suggested_email': suggested['owner_email'],
            'suggested_phone': suggested['owner_phone'],
            'has_dog': suggested['has_dog'],
            'import_mode': 'customer_and_dog' if suggested['has_dog'] else 'customer_only',
            'import_status': import_status,
            'can_import': can_import,
        }
        selectable_contacts.append(entry)
        if name_issues:
            name_issues_count += 1
            name_review_contacts.append(entry)

    return ImportAnalysis(
        contacts=contacts,
        csv_email_duplicates=csv_email_dups,
        csv_phone_duplicates=csv_phone_dups,
        db_email_matches=db_email_matches,
        db_phone_matches=db_phone_matches,
        new_contacts=new_contacts,
        selectable_contacts=selectable_contacts,
        name_review_contacts=name_review_contacts,
        total_rows=len(contacts),
        skipped_rows=skipped,
        name_issues_count=name_issues_count,
    )


def build_vcard(client: ClientProfile) -> str:
    """Build a vCard 3.0 file for double-click import into Google Contacts."""
    name_parts = client.owner_name.split(None, 1)
    first = name_parts[0] if name_parts else client.owner_name
    last = name_parts[1] if len(name_parts) > 1 else ''

    lines = [
        'BEGIN:VCARD',
        'VERSION:3.0',
        f'N:{last};{first};;;',
        f'FN:{client.owner_name}',
        f'ORG:Dad4dogs Client',
        f'TITLE:Dog: {client.dog_name}',
    ]
    if client.owner_email:
        lines.append(f'EMAIL;TYPE=INTERNET:{client.owner_email}')
    if client.owner_phone:
        lines.append(f'TEL;TYPE=CELL:{client.owner_phone}')
    if client.notes:
        note = client.notes.replace('\n', '\\n')
        lines.append(f'NOTE:Dog: {client.dog_name}. {note}')
    else:
        lines.append(f'NOTE:Dog: {client.dog_name}')

    lines.append('END:VCARD')
    return '\r\n'.join(lines) + '\r\n'


def analysis_to_session(analysis: ImportAnalysis) -> dict:
    """Serialize analysis for session storage (preview only, no DB import)."""

    def contact_dict(c: ParsedContact) -> dict:
        return {
            'row_number': c.row_number,
            'display_name': c.display_name,
            'first_name': c.first_name,
            'last_name': c.last_name,
            'emails': c.emails,
            'phones': c.phones,
            'notes': c.notes[:200],
        }

    def group_dict(g: DuplicateGroup) -> dict:
        return {
            'match_type': g.match_type,
            'match_value': g.match_value,
            'source': g.source,
            'contacts': [contact_dict(c) for c in g.contacts],
            'existing_clients': [
                {
                    'id': cl.pk,
                    'dog_name': cl.dog_name,
                    'owner_name': cl.owner_name,
                    'owner_email': cl.owner_email,
                    'owner_phone': cl.owner_phone,
                }
                for cl in g.existing_clients
            ],
            'existing_owners': [
                {
                    'id': o.pk,
                    'owner_name': o.owner_name,
                    'owner_email': o.owner_email,
                    'owner_phone': o.owner_phone,
                }
                for o in g.existing_owners
            ],
        }

    return {
        'total_rows': analysis.total_rows,
        'skipped_rows': analysis.skipped_rows,
        'new_count': len(analysis.new_contacts),
        'name_issues_count': analysis.name_issues_count,
        'csv_email_duplicates': [group_dict(g) for g in analysis.csv_email_duplicates],
        'csv_phone_duplicates': [group_dict(g) for g in analysis.csv_phone_duplicates],
        'db_email_matches': [group_dict(g) for g in analysis.db_email_matches],
        'db_phone_matches': [group_dict(g) for g in analysis.db_phone_matches],
        'new_contacts': [contact_dict(c) for c in analysis.new_contacts],
        'selectable_contacts': analysis.selectable_contacts,
        'name_review_contacts': analysis.name_review_contacts,
    }


def import_selected_contacts(
    selectable_contacts: list[dict],
    selected_rows: list[int],
    overrides: dict[int, dict],
) -> tuple[list[CustomerOwner], list[ClientProfile], list[str]]:
    """
    Import selected CSV rows as customers. Dogs are only created with a valid dog name.

    Returns (created customers, created dogs, error messages).
    """
    by_row = {c['row_number']: c for c in selectable_contacts}
    created_owners = []
    created_dogs = []
    errors = []

    for row_num in selected_rows:
        contact = by_row.get(row_num)
        if not contact:
            errors.append(f'Row {row_num}: not found in import session.')
            continue
        if not contact['can_import']:
            errors.append(f'Row {row_num}: already in system or cannot be imported.')
            continue

        override = overrides.get(row_num, {})
        dog_name = (override.get('dog_name') or contact['suggested_dog_name'] or '').strip()
        owner_name = override.get('owner_name') or contact['suggested_owner_name']
        email = contact['suggested_email']
        phone = override.get('owner_phone') or contact['suggested_phone']

        if not email:
            errors.append(f'Row {row_num}: email required.')
            continue
        if not owner_name:
            errors.append(f'Row {row_num}: owner name required.')
            continue

        owner, created = CustomerOwner.objects.get_or_create(
            owner_email=email.strip().lower(),
            defaults={
                'owner_name': owner_name.strip(),
                'owner_phone': (phone or '').strip(),
            },
        )
        if not created:
            owner.owner_name = owner_name.strip()
            owner.owner_phone = (phone or '').strip()
            owner.save(update_fields=['owner_name', 'owner_phone', 'updated_at'])
        if created:
            created_owners.append(owner)

        if is_valid_dog_name(dog_name, owner_name):
            if ClientProfile.objects.filter(
                owner_email__iexact=email,
                dog_name__iexact=dog_name,
            ).exists():
                errors.append(f'Row {row_num}: dog {dog_name} already exists.')
                continue

            note_parts = []
            if contact['notes']:
                note_parts.append(contact['notes'])
            if contact['name_issues']:
                note_parts.append('Name flags: ' + '; '.join(contact['name_issues']))

            dog = ClientProfile.objects.create(
                dog_name=dog_name,
                owner_name=owner.owner_name,
                owner_email=owner.owner_email,
                owner_phone=owner.owner_phone,
                notes='\n'.join(note_parts).strip()[:2000],
                pipeline_stage=ClientProfile.PipelineStage.INQUIRY,
            )
            created_dogs.append(dog)

    return created_owners, created_dogs, errors