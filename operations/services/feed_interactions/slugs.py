import secrets
import string
import uuid

from django.utils.text import slugify

_SHARE_TOKEN_ALPHABET = string.ascii_letters + string.digits

# Pronounceable feed secrets: stacked CV syllables (consonant + vowel), ngrok-style.
# Two chunks smashed together → squeakytiki, bokomelu, zafupiko.
_CONSONANTS = 'bcdfghjklmnprstvwz'
_VOWELS = 'aeiou'


def _cv_syllable() -> str:
    return secrets.choice(_CONSONANTS) + secrets.choice(_VOWELS)


def _speakable_chunk(*, min_syllables: int = 2, max_syllables: int = 3) -> str:
    count = secrets.randbelow(max_syllables - min_syllables + 1) + min_syllables
    return ''.join(_cv_syllable() for _ in range(count))


def dog_slug_from_name(dog_name: str) -> str:
    """URL segment for the pet name (e.g. Lulu → lulu, Mr. Biscuit → mr-biscuit)."""
    slug = slugify((dog_name or '').strip()) or 'dog'
    return slug[:80]


def generate_feed_secret() -> str:
    """Return a random speakable slug like bokomelu or zafupiko."""
    return _speakable_chunk() + _speakable_chunk()


def generate_share_token(length: int = 16) -> str:
    """Short opaque public share key (e.g. eXIvE692WTJul1JvM)."""
    return ''.join(secrets.choice(_SHARE_TOKEN_ALPHABET) for _ in range(length))


def generate_unique_share_token(*, max_attempts: int = 40) -> str:
    from operations.models.scheduling import SharedMediaLink

    for _ in range(max_attempts):
        candidate = generate_share_token()
        if not SharedMediaLink.objects.filter(share_token=candidate).exists():
            return candidate
    return uuid.uuid4().hex[:16]


def generate_unique_feed_secret(*, max_attempts: int = 40) -> str:
    from operations.models.customers import ClientProfile

    for _ in range(max_attempts):
        candidate = generate_feed_secret()
        if not ClientProfile.objects.filter(feed_secret=candidate).exists():
            return candidate
    # ~8 dogs / ~30 customers — collisions should never happen; UUID is the last resort.
    return uuid.uuid4().hex