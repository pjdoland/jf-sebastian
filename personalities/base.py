"""
Base personality class and YAML loader for animatronic characters.
Personalities are defined in personality.yaml files within each personality directory.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import yaml


@dataclass
class Personality:
    """
    Personality configuration for an animatronic character.
    Loaded from personality.yaml files.
    """

    name: str
    """Character name (e.g., 'Johnny', 'Mr. Lincoln')"""

    tts_voice: str
    """OpenAI TTS voice ID (e.g., 'onyx', 'echo', 'fable')"""

    wake_word_model: str
    """Filename of the wake word model (.onnx) in the personality directory"""

    system_prompt: str
    """System prompt that defines the character's personality for the LLM"""

    filler_phrases: List[str]
    """List of filler phrases for low-latency responses"""

    personality_dir: Path
    """Directory containing this personality's files"""

    tts_speed: float = 1.0
    """TTS speech speed (0.25 to 4.0, default 1.0)"""

    tts_style: Optional[str] = None
    """Optional style instruction prepended to TTS input (e.g., 'speaking warmly and casually')"""

    @property
    def wake_word_model_paths(self) -> List[Path]:
        """Get full paths to wake word model files"""
        return [self.personality_dir / self.wake_word_model]

    @property
    def filler_audio_dir(self) -> Path:
        """Directory containing pre-generated filler audio files"""
        return self.personality_dir / "filler_audio"

    def get_description(self) -> str:
        """Get a human-readable description of this personality"""
        first_sentence = self.system_prompt.split('.')[0] if self.system_prompt else ""
        return f"{self.name} - {first_sentence}"


def load_personality_from_yaml(personality_dir: Path) -> Personality:
    """
    Load a personality from a personality.yaml file.

    Args:
        personality_dir: Path to the personality directory

    Returns:
        Personality instance

    Raises:
        FileNotFoundError: If personality.yaml doesn't exist
        ValueError: If YAML is invalid or missing required fields
    """
    yaml_path = personality_dir / "personality.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(f"No personality.yaml found in {personality_dir}")

    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Validate required fields
    required_fields = ['name', 'tts_voice', 'wake_word_model', 'system_prompt', 'filler_phrases']
    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        raise ValueError(
            f"personality.yaml in {personality_dir} is missing required fields: "
            f"{', '.join(missing_fields)}"
        )

    # Validate filler_phrases is a list
    if not isinstance(data['filler_phrases'], list):
        raise ValueError(
            f"personality.yaml in {personality_dir}: 'filler_phrases' must be a list"
        )

    # Get optional TTS settings with defaults
    tts_speed = data.get('tts_speed', 1.0)
    tts_style = data.get('tts_style', None)

    # Validate tts_speed if provided
    if tts_speed < 0.25 or tts_speed > 4.0:
        raise ValueError(
            f"personality.yaml in {personality_dir}: 'tts_speed' must be between 0.25 and 4.0"
        )

    # Create Personality instance
    return Personality(
        name=data['name'],
        tts_voice=data['tts_voice'],
        wake_word_model=data['wake_word_model'],
        system_prompt=data['system_prompt'],
        filler_phrases=data['filler_phrases'],
        personality_dir=personality_dir,
        tts_speed=tts_speed,
        tts_style=tts_style
    )


def discover_personalities(personalities_root: Path) -> dict[str, Path]:
    """
    Auto-discover all personality directories containing personality.yaml files.

    Args:
        personalities_root: Root directory containing personality folders

    Returns:
        Dictionary mapping personality names (lowercase folder names) to their directories
    """
    personalities = {}

    if not personalities_root.exists():
        return personalities

    # Look for subdirectories containing personality.yaml
    for item in personalities_root.iterdir():
        if item.is_dir() and not item.name.startswith(('_', '.')):
            yaml_file = item / "personality.yaml"
            if yaml_file.exists():
                # Use folder name as personality key
                personality_key = item.name.lower()
                personalities[personality_key] = item

    return personalities
