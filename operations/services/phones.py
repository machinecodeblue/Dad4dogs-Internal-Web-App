"""North American phone numbers — normalize, validate, display, tel: href."""

from __future__ import annotations

import re

NANP_MESSAGE = 'Enter a 10-digit North American number.'


def normalize_phone(phone: str) -> str:
    """Digits-only NANP national number. Strips a leading country code 1."""
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def is_valid_nanp(digits: str) -> bool:
    return (
        len(digits) == 10
        and digits.isdigit()
        and digits[0] not in '01'
        and digits[3] not in '01'
    )


def validate_phone(
    phone: str,
    *,
    required: bool = False,
    required_message: str = 'Phone number is required.',
) -> str:
    """Return a 10-digit NANP number, or '' if blank and not required."""
    raw = (phone or '').strip()
    if not raw:
        if required:
            raise ValueError(required_message)
        return ''
    digits = normalize_phone(raw)
    if not is_valid_nanp(digits):
        raise ValueError(NANP_MESSAGE)
    return digits


def format_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if is_valid_nanp(digits):
        return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    return (phone or '').strip()


def e164(phone: str) -> str:
    """`+1XXXXXXXXXX` for valid NANP; otherwise the original trimmed value."""
    digits = normalize_phone(phone)
    if is_valid_nanp(digits):
        return f'+1{digits}'
    return (phone or '').strip()


def tel_href(phone: str) -> str:
    """`tel:+1XXXXXXXXXX` for valid NANP; otherwise best-effort `tel:`."""
    digits = normalize_phone(phone)
    if is_valid_nanp(digits):
        return f'tel:+1{digits}'
    if digits:
        return f'tel:{digits}'
    raw = (phone or '').strip()
    return f'tel:{raw}' if raw else ''
