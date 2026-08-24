"""Canadian home-address helpers — format, postal normalize, maps URL, legacy parse."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

CANADIAN_PROVINCES = [
    ('AB', 'Alberta'),
    ('BC', 'British Columbia'),
    ('MB', 'Manitoba'),
    ('NB', 'New Brunswick'),
    ('NL', 'Newfoundland and Labrador'),
    ('NS', 'Nova Scotia'),
    ('NT', 'Northwest Territories'),
    ('NU', 'Nunavut'),
    ('ON', 'Ontario'),
    ('PE', 'Prince Edward Island'),
    ('QC', 'Quebec'),
    ('SK', 'Saskatchewan'),
    ('YT', 'Yukon'),
]

PROVINCE_CODES = {code for code, _label in CANADIAN_PROVINCES}

PROVINCE_ALIASES = {
    'alberta': 'AB',
    'british columbia': 'BC',
    'manitoba': 'MB',
    'new brunswick': 'NB',
    'newfoundland': 'NL',
    'newfoundland and labrador': 'NL',
    'nova scotia': 'NS',
    'northwest territories': 'NT',
    'nunavut': 'NU',
    'ontario': 'ON',
    'ont': 'ON',
    'prince edward island': 'PE',
    'pei': 'PE',
    'quebec': 'QC',
    'québec': 'QC',
    'saskatchewan': 'SK',
    'yukon': 'YT',
}

# First letter excludes D, F, I, O, Q, U, W, Z. Other letters exclude D, F, I, O, Q, U.
_POSTAL_BODY = (
    r'([ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z])'
    r'[ -]?'
    r'(\d[ABCEGHJ-NPRSTV-Z]\d)'
)
POSTAL_RE = re.compile(rf'^{_POSTAL_BODY}$', re.IGNORECASE)
POSTAL_SEARCH = re.compile(rf'\b{_POSTAL_BODY}\b', re.IGNORECASE)

_UNIT_PREFIX = re.compile(r'^(unit|apt\.?|apartment|suite|#)\b', re.IGNORECASE)
_UNIT_IN_STREET = re.compile(
    r'[,\s]+(?:unit|apt\.?|apartment|suite|#)\s*([A-Za-z0-9-]+)\s*$',
    re.IGNORECASE,
)
_TRAILING_CITY_PROVINCE = re.compile(
    r'[\s,]+([A-Za-z][A-Za-z .\'-]*?)\s*,?\s+'
    r'(ON|Ontario|Ont|QC|Quebec|Québec|BC|AB|MB|SK|NS|NB|NL|PE|PEI|YT|NT|NU|'
    r'British Columbia|Alberta|Manitoba|Saskatchewan|Nova Scotia|'
    r'New Brunswick|Newfoundland(?: and Labrador)?|Prince Edward Island|'
    r'Yukon|Northwest Territories|Nunavut)\s*$',
    re.IGNORECASE,
)


def normalize_province(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''
    upper = raw.upper()
    if upper in PROVINCE_CODES:
        return upper
    alias = PROVINCE_ALIASES.get(raw.lower())
    if alias:
        return alias
    raise ValueError('Enter a Canadian province or territory.')


def normalize_postal_code(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''
    compact = re.sub(r'[\s-]+', '', raw).upper()
    match = POSTAL_RE.match(f'{compact[:3]} {compact[3:]}' if len(compact) == 6 else compact)
    if not match:
        raise ValueError('Enter a Canadian postal code like N6B 1G2.')
    return f'{match.group(1).upper()} {match.group(2).upper()}'


def format_unit(unit: str) -> str:
    raw = (unit or '').strip()
    if not raw:
        return ''
    if _UNIT_PREFIX.match(raw):
        return raw
    return f'Unit {raw}'


def format_address(
    *,
    street: str = '',
    unit: str = '',
    city: str = '',
    province: str = '',
    postal: str = '',
    oneline: bool = False,
) -> str:
    street = (street or '').strip()
    unit_label = format_unit(unit)
    city = (city or '').strip()
    province = (province or '').strip().upper()
    postal = (postal or '').strip().upper()

    street_line = street
    if unit_label:
        street_line = f'{street}, {unit_label}' if street else unit_label

    locality_parts = []
    if city and province:
        locality_parts.append(f'{city}, {province}')
    elif city:
        locality_parts.append(city)
    elif province:
        locality_parts.append(province)
    if postal:
        locality_parts.append(postal)
    locality_line = ' '.join(locality_parts)

    if oneline:
        return ', '.join(part for part in (street_line, locality_line) if part)

    return '\n'.join(part for part in (street_line, locality_line) if part)


def maps_search_url(address: str) -> str:
    query = (address or '').strip()
    if not query:
        return ''
    oneline = ', '.join(line.strip() for line in query.splitlines() if line.strip())
    return f'https://www.google.com/maps/search/?api=1&query={quote_plus(oneline)}'


def parse_legacy_address(text: str) -> dict[str, str]:
    """Best-effort split of free-text `home_address` into structured parts."""
    result = {
        'street': '',
        'unit': '',
        'city': '',
        'province': '',
        'postal': '',
    }
    remainder = (text or '').strip()
    if not remainder:
        return result

    postal_match = POSTAL_SEARCH.search(remainder)
    if postal_match:
        try:
            result['postal'] = normalize_postal_code(postal_match.group(0))
        except ValueError:
            result['postal'] = ''
        else:
            remainder = (
                remainder[:postal_match.start()] + remainder[postal_match.end():]
            ).strip(' ,\n\t')

    remainder = re.sub(r'[,\s]+$', '', remainder).strip()
    loc_match = _TRAILING_CITY_PROVINCE.search(remainder)
    if loc_match:
        result['city'] = loc_match.group(1).strip(' ,')
        try:
            result['province'] = normalize_province(loc_match.group(2))
        except ValueError:
            result['province'] = ''
        remainder = remainder[:loc_match.start()].strip(' ,\n\t')

    unit_match = _UNIT_IN_STREET.search(remainder)
    if unit_match:
        result['unit'] = unit_match.group(1).strip()
        remainder = remainder[:unit_match.start()].strip(' ,')

    result['street'] = re.sub(r'\s+', ' ', remainder).strip(' ,')
    return result
