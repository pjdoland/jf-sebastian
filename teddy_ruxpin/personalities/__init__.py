"""
Personality system for animatronic characters.
Each personality has its own wake word, system prompt, filler phrases, and voice.
"""

from .base import Personality
from .johnny import JohnnyPersonality
from .rich import RichPersonality


# Registry of available personalities
PERSONALITIES = {
    "johnny": JohnnyPersonality,
    "rich": RichPersonality,
}


def get_personality(name: str) -> Personality:
    """
    Get a personality instance by name.

    Args:
        name: Personality name (e.g., 'johnny', 'rich')

    Returns:
        Personality instance

    Raises:
        ValueError: If personality name is not found
    """
    name_lower = name.lower()
    if name_lower not in PERSONALITIES:
        available = ", ".join(PERSONALITIES.keys())
        raise ValueError(f"Unknown personality '{name}'. Available: {available}")

    personality_class = PERSONALITIES[name_lower]
    return personality_class()


def list_personalities() -> list[str]:
    """Get list of available personality names"""
    return list(PERSONALITIES.keys())


__all__ = [
    'Personality',
    'JohnnyPersonality',
    'RichPersonality',
    'get_personality',
    'list_personalities',
    'PERSONALITIES',
]
