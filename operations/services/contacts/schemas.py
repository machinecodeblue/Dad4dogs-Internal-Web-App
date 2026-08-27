from dataclasses import dataclass, field
from operations.models import ClientProfile, CustomerOwner

GOOGLE_CSV_FIELDS = [
    'First Name', 'Middle Name', 'Last Name',
    'E-mail 1 - Value', 'E-mail 2 - Value',
    'Phone 1 - Value', 'Notes',
]

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