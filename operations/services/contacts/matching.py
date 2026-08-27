from operations.models import ClientProfile, CustomerOwner
from operations.services.phones import normalize_phone
from .heuristics import assess_name_quality, suggest_client_fields
from .parsers import normalize_email
from .schemas import DuplicateGroup, ImportAnalysis, ParsedContact


def _group_by_field(contacts: list[ParsedContact], field: str, match_type: str, source: str) -> list[DuplicateGroup]:
    buckets: dict[str, list[ParsedContact]] = {}
    getter = (lambda c: c.normalized_emails) if field == 'email' else (lambda c: c.normalized_phones)

    for contact in contacts:
        for value in getter(contact):
            if value:
                buckets.setdefault(value, []).append(contact)

    groups = []
    for value, members in buckets.items():
        if len({c.row_number for c in members}) > 1:
            groups.append(DuplicateGroup(
                match_type=match_type,
                match_value=value,
                contacts=members,
                source=source,
            ))
    return sorted(groups, key=lambda g: g.match_value)


def _match_against_db(contacts: list[ParsedContact], field: str, match_type: str) -> list[DuplicateGroup]:
    groups = []
    seen: set[tuple[str, int]] = set()

    if field == 'email':
        db_index: dict[str, list[ClientProfile]] = {}
        for client in ClientProfile.objects.all():
            db_index.setdefault(normalize_email(client.owner_email), []).append(client)
        owner_index = {normalize_email(o.owner_email): o for o in CustomerOwner.objects.all()}
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
            clients = db_index.get(value, [])
            owner = owner_index.get(value) if field == 'email' else None

            if not clients and owner:
                dedupe_key = (value, owner.pk)
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    groups.append(DuplicateGroup(
                        match_type=match_type,
                        match_value=value,
                        contacts=[contact],
                        existing_owners=[owner],
                        source='database',
                    ))
            elif clients:
                for client in clients:
                    dedupe_key = (value, client.pk)
                    if dedupe_key not in seen:
                        seen.add(dedupe_key)
                        groups.append(DuplicateGroup(
                            match_type=match_type,
                            match_value=value,
                            contacts=[contact],
                            existing_clients=[client],
                            source='database',
                        ))

    return sorted(groups, key=lambda g: (g.match_value, g.contacts[0].row_number))


def analyze_import(contacts: list[ParsedContact], skipped: int = 0) -> ImportAnalysis:
    csv_email_dups = _group_by_field(contacts, 'email', 'email', 'csv')
    csv_phone_dups = _group_by_field(contacts, 'phone', 'phone', 'csv')
    db_email_matches = _match_against_db(contacts, 'email', 'email')
    db_phone_matches = _match_against_db(contacts, 'phone', 'phone')

    csv_dup_rows = {c.row_number for g in csv_email_dups + csv_phone_dups for c in g.contacts}
    db_matched_rows = {c.row_number for g in db_email_matches + db_phone_matches for c in g.contacts}

    new_contacts = [c for c in contacts if c.row_number not in (csv_dup_rows | db_matched_rows)]
    selectable, review_list, issues_count = [], [], 0

    for contact in contacts:
        issues = assess_name_quality(contact)
        sug = suggest_client_fields(contact)
        email = sug.get('owner_email', '')

        if not email:
            import_status, can_import = 'no_email', False
        elif CustomerOwner.objects.filter(owner_email__iexact=email).exists():
            import_status, can_import = ('in_db' if sug.get('has_dog') else 'customer_exists'), False
        elif contact.row_number in db_matched_rows:
            import_status, can_import = 'in_db', False
        elif contact.row_number in csv_dup_rows:
            import_status, can_import = 'csv_duplicate', True
        else:
            import_status, can_import = 'new', True

        entry = {
            'row_number': contact.row_number,
            'display_name': contact.display_name,
            'first_name': contact.first_name,
            'middle_name': contact.middle_name,
            'last_name': contact.last_name,
            'emails': contact.emails,
            'phones': contact.phones,
            'notes': contact.notes[:300],
            'name_issues': issues,
            'needs_name_review': bool(issues),
            'suggested_dog_name': sug['dog_name'],
            'suggested_owner_name': sug['owner_name'],
            'suggested_email': sug['owner_email'],
            'suggested_phone': sug['owner_phone'],
            'has_dog': sug['has_dog'],
            'import_mode': 'customer_and_dog' if sug['has_dog'] else 'customer_only',
            'import_status': import_status,
            'can_import': can_import,
        }
        selectable.append(entry)
        if issues:
            issues_count += 1
            review_list.append(entry)

    return ImportAnalysis(
        contacts=contacts,
        csv_email_duplicates=csv_email_dups,
        csv_phone_duplicates=csv_phone_dups,
        db_email_matches=db_email_matches,
        db_phone_matches=db_phone_matches,
        new_contacts=new_contacts,
        selectable_contacts=selectable,
        name_review_contacts=review_list,
        total_rows=len(contacts),
        skipped_rows=skipped,
        name_issues_count=issues_count,
    )