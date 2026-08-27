import re
from .schemas import DOG_NICKNAME_KEYWORDS, INFORMAL_ONLY_NAMES, ParsedContact


def is_valid_dog_name(dog_name: str, owner_name: str) -> bool:
    """A dog record is only created when we have a real dog name."""
    if not dog_name or dog_name.strip().upper() in ('TBD', 'UNKNOWN'):
        return False
    parts = (owner_name or '').split()
    owner_first = parts[0].lower() if parts else ''
    stripped = dog_name.strip()
    return bool(stripped) and stripped.lower() != owner_first


def extract_dog_from_notes(notes: str) -> str:
    match = re.search(r"dog'?s name is ([^.,\n;]+)", notes, re.IGNORECASE)
    return match.group(1).strip() if match else ''


def first_looks_like_dog_nickname(first_name: str) -> bool:
    lower = first_name.lower()
    words = set(re.split(r'[\s\-]+', lower))
    if words & DOG_NICKNAME_KEYWORDS:
        return True
    if any(kw in lower for kw in DOG_NICKNAME_KEYWORDS):
        return True
    return lower.endswith(' contact')


def assess_name_quality(contact: ParsedContact) -> list[str]:
    issues = []
    if not contact.first_name and not contact.last_name:
        return ['No name recorded']
    if contact.first_name and not contact.last_name:
        issues.append("Missing last name — confirm owner's full name")
    if first_looks_like_dog_nickname(contact.first_name):
        issues.append('First name looks like a dog nickname, not an owner')
    if contact.first_name and len(contact.first_name.split()) >= 3:
        issues.append('First name has multiple words — may be a description')
    if contact.first_name.lower() in INFORMAL_ONLY_NAMES and not contact.last_name:
        issues.append('Only a first name on file — get full name when you speak')

    dog_in_notes = extract_dog_from_notes(contact.notes)
    if dog_in_notes and dog_in_notes.lower() != contact.first_name.lower():
        issues.append(f'Notes say dog is "{dog_in_notes}" — names may be swapped')
    if contact.middle_name and contact.middle_name.lower() in {'golden', 'doodle', 'labrador', 'retriever'}:
        issues.append('Breed appears in name fields — dog vs owner unclear')
    if contact.first_name and contact.last_name and not first_looks_like_dog_nickname(contact.first_name) and not dog_in_notes:
        issues.append(f'"{contact.first_name} {contact.last_name}" looks like the owner — add a dog separately')
    if not issues and contact.first_name and contact.last_name and (contact.first_name.islower() or contact.last_name.islower()):
        issues.append('Name not properly capitalized — verify spelling')

    return issues


def suggest_client_fields(contact: ParsedContact) -> dict:
    dog_in_notes = extract_dog_from_notes(contact.notes)
    first, last, middle = contact.first_name, contact.last_name, contact.middle_name

    if dog_in_notes:
        dog_name = dog_in_notes
        owner_parts = [p for p in [first, middle, last] if p]
        owner_name = ' '.join(owner_parts) if owner_parts else contact.display_name
    elif first_looks_like_dog_nickname(first) and last:
        dog_name = first
        owner_name = last if not middle else f'{middle} {last}'.strip()
    elif first and last and not first_looks_like_dog_nickname(first):
        dog_name = ''
        owner_name = ' '.join(p for p in [first, middle, last] if p)
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