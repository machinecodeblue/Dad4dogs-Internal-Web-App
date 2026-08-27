from .schemas import DuplicateGroup, ImportAnalysis, ParsedContact


def _contact_dict(c: ParsedContact) -> dict:
    return {
        'row_number': c.row_number,
        'display_name': c.display_name,
        'first_name': c.first_name,
        'last_name': c.last_name,
        'emails': c.emails,
        'phones': c.phones,
        'notes': c.notes[:200],
    }


def _group_dict(g: DuplicateGroup) -> dict:
    return {
        'match_type': g.match_type,
        'match_value': g.match_value,
        'source': g.source,
        'contacts': [_contact_dict(c) for c in g.contacts],
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


def analysis_to_session(analysis: ImportAnalysis) -> dict:
    """Serialize analysis for preview session storage (no DB writes)."""
    return {
        'total_rows': analysis.total_rows,
        'skipped_rows': analysis.skipped_rows,
        'new_count': len(analysis.new_contacts),
        'name_issues_count': analysis.name_issues_count,
        'csv_email_duplicates': [_group_dict(g) for g in analysis.csv_email_duplicates],
        'csv_phone_duplicates': [_group_dict(g) for g in analysis.csv_phone_duplicates],
        'db_email_matches': [_group_dict(g) for g in analysis.db_email_matches],
        'db_phone_matches': [_group_dict(g) for g in analysis.db_phone_matches],
        'new_contacts': [_contact_dict(c) for c in analysis.new_contacts],
        'selectable_contacts': analysis.selectable_contacts,
        'name_review_contacts': analysis.name_review_contacts,
    }