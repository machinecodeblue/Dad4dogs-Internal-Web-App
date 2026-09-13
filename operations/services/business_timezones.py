"""
Curated IANA timezone catalog for Business Settings.

Independent of BusinessProfile.address — operators in CA / US / UK / AU
pick a zone even when address is blank. Labels are for humans; values are
IANA ids stored on BusinessProfile.timezone.
"""

DEFAULT_BUSINESS_TIMEZONE = 'America/Toronto'

# (iana_id, human_label) — searchable in Settings via datalist / filter.
BUSINESS_TIMEZONE_CHOICES = [
    # Canada
    ('America/St_Johns', 'Canada — Newfoundland Time (St. John\'s)'),
    ('America/Halifax', 'Canada — Atlantic Time (Halifax)'),
    ('America/Toronto', 'Canada — Eastern Time (Toronto)'),
    ('America/Winnipeg', 'Canada — Central Time (Winnipeg)'),
    ('America/Edmonton', 'Canada — Mountain Time (Calgary / Edmonton)'),
    ('America/Vancouver', 'Canada — Pacific Time (Vancouver)'),
    # United States
    ('America/New_York', 'United States — Eastern Time (New York)'),
    ('America/Chicago', 'United States — Central Time (Chicago)'),
    ('America/Denver', 'United States — Mountain Time (Denver)'),
    ('America/Phoenix', 'United States — Mountain Time, no DST (Phoenix)'),
    ('America/Los_Angeles', 'United States — Pacific Time (Los Angeles)'),
    ('America/Anchorage', 'United States — Alaska Time (Anchorage)'),
    ('Pacific/Honolulu', 'United States — Hawaii Time (Honolulu)'),
    # United Kingdom & Ireland
    ('Europe/London', 'United Kingdom — UK Time (London)'),
    ('Europe/Dublin', 'Ireland — Ireland Time (Dublin)'),
    # Australia
    ('Australia/Sydney', 'Australia — Eastern Time (Sydney)'),
    ('Australia/Melbourne', 'Australia — Eastern Time (Melbourne)'),
    ('Australia/Brisbane', 'Australia — Eastern Time, no DST (Brisbane)'),
    ('Australia/Adelaide', 'Australia — Central Time (Adelaide)'),
    ('Australia/Darwin', 'Australia — Central Time, no DST (Darwin)'),
    ('Australia/Perth', 'Australia — Western Time (Perth)'),
]

BUSINESS_TIMEZONE_VALUES = frozenset(value for value, _label in BUSINESS_TIMEZONE_CHOICES)

# For datalist search: show "Label (iana)" so typing "London" or "Europe/London" both match.
BUSINESS_TIMEZONE_DATALIST = [
    f'{label} ({value})' for value, label in BUSINESS_TIMEZONE_CHOICES
]


def label_for_timezone(iana_id: str) -> str:
    for value, label in BUSINESS_TIMEZONE_CHOICES:
        if value == iana_id:
            return label
    return iana_id or DEFAULT_BUSINESS_TIMEZONE


def parse_timezone_search_value(raw: str) -> str:
    """
    Map a datalist display string or raw IANA id to a catalog value.

    Accepts:
    - ``America/Toronto``
    - ``Canada — Eastern Time (Toronto) (America/Toronto)``
    """
    text = (raw or '').strip()
    if not text:
        return ''
    if text in BUSINESS_TIMEZONE_VALUES:
        return text
    if text.endswith(')') and '(' in text:
        maybe = text.rsplit('(', 1)[-1].rstrip(')').strip()
        if maybe in BUSINESS_TIMEZONE_VALUES:
            return maybe
    for value, label in BUSINESS_TIMEZONE_CHOICES:
        if text == label or text.lower() == label.lower():
            return value
    return text
