"""
Personality system for animatronic characters.

Personalities are automatically discovered from subdirectories containing personality.yaml files.
Just drop a new personality folder into personalities/ and it will be available!
"""

from pathlib import Path
from .base import Personality, load_personality_from_yaml, discover_personalities


# Auto-discover all personalities in this directory
_PERSONALITIES_ROOT = Path(__file__).parent
_PERSONALITY_CACHE = {}  # Cache loaded personalities


def get_personality(name: str) -> Personality:
    """
    Get a personality instance by name.

    Personalities are automatically discovered from subdirectories containing personality.yaml.

    Args:
        name: Personality name (e.g., 'johnny', 'mr_lincoln', 'leopold') - matches folder name

    Returns:
        Personality instance loaded from personality.yaml

    Raises:
        ValueError: If personality name is not found or YAML is invalid
    """
    name_lower = name.lower()

    # Check cache first
    if name_lower in _PERSONALITY_CACHE:
        return _PERSONALITY_CACHE[name_lower]

    # Discover available personalities
    available_personalities = discover_personalities(_PERSONALITIES_ROOT)

    if name_lower not in available_personalities:
        available = ", ".join(available_personalities.keys())
        raise ValueError(f"Unknown personality '{name}'. Available: {available}")

    # Load personality from YAML
    personality_dir = available_personalities[name_lower]
    try:
        personality = load_personality_from_yaml(personality_dir)
        _PERSONALITY_CACHE[name_lower] = personality
        return personality
    except Exception as e:
        raise ValueError(f"Failed to load personality '{name}': {e}")


def list_personalities() -> list[str]:
    """
    Get list of available personality names.

    Returns:
        List of personality folder names (lowercase)
    """
    available_personalities = discover_personalities(_PERSONALITIES_ROOT)
    return sorted(available_personalities.keys())


__all__ = [
    'Personality',
    'get_personality',
    'list_personalities',
]
