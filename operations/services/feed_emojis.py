"""
Reaction emoji maps — dog-themed in the feed UI, standard when summarized/shared.
Replace DOG_EMOJI values with custom dog artwork paths when assets are ready.
"""
from operations.models import MediaReaction

REACTION_ORDER = [choice.value for choice in MediaReaction.Emoji]

# In-app reaction bar (dog-themed; swap for custom PNG/SVG later)
DOG_EMOJI: dict[str, str] = {
    'like': '🐾',
    'love': '🐕',
    'haha': '🐶',
    'wow': '🦴',
    'sad': '🥺',
}

# Counts, check-in activity, and anything "shared outward"
STANDARD_EMOJI: dict[str, str] = {
    'like': '👍',
    'love': '❤️',
    'haha': '😂',
    'wow': '😮',
    'sad': '😢',
}


def reaction_choices_for_feed() -> list[tuple[str, str, str]]:
    """(storage key, dog display glyph, standard shared glyph)."""
    return [(key, DOG_EMOJI[key], STANDARD_EMOJI[key]) for key in REACTION_ORDER]


def standard_emoji_label(emoji_key: str) -> str:
    return STANDARD_EMOJI.get(emoji_key, emoji_key)


def dog_emoji_label(emoji_key: str) -> str:
    return DOG_EMOJI.get(emoji_key, emoji_key)