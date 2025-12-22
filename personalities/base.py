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
    """Optional style instruction for gpt-4o-mini-tts model (e.g., 'Speak warmly and casually')"""

    # RVC Voice Conversion (optional)
    rvc_enabled: bool = False
    """Enable RVC voice conversion for this personality"""

    rvc_model: Optional[str] = None
    """RVC model filename (.pth) - looked up in personality dir, then global rvc_models/"""

    rvc_index_file: Optional[str] = None
    """RVC index filename (.index) - optional, looked up in personality dir"""

    rvc_pitch_shift: int = 0
    """RVC pitch shift in semitones (-12 to +12)"""

    rvc_index_rate: float = 0.5
    """RVC feature retrieval influence (0.0 to 1.0)"""

    rvc_f0_method: str = "harvest"
    """RVC pitch extraction method (harvest/crepe/pm/dio/rmvpe)"""

    rvc_filter_radius: int = 3
    """RVC median filtering radius for pitch (0-7, lower = faster)"""

    rvc_rms_mix_rate: float = 0.25
    """RVC volume envelope mix rate (0.0 to 1.0, lower = faster)"""

    rvc_protect: float = 0.33
    """RVC voiceless consonant protection (0.0 to 0.5, lower = faster)"""

    @property
    def wake_word_model_paths(self) -> List[Path]:
        """Get full paths to wake word model files"""
        return [self.personality_dir / self.wake_word_model]

    @property
    def filler_audio_dir(self) -> Path:
        """Directory containing pre-generated filler audio files"""
        return self.personality_dir / "filler_audio"

    @property
    def rvc_model_path(self) -> Optional[Path]:
        """
        Get full path to RVC model file.
        Checks personality directory first, then global rvc_models/ directory.
        Returns None if model not specified or not found.
        """
        if not self.rvc_model:
            return None

        # Check personality directory first
        personality_model = self.personality_dir / self.rvc_model
        if personality_model.exists():
            return personality_model

        # Check global RVC models directory
        from jf_sebastian.config import settings
        global_model = settings.RVC_MODEL_DIR / self.rvc_model
        if global_model.exists():
            return global_model

        # Model not found in either location
        return None

    @property
    def rvc_index_path(self) -> Optional[Path]:
        """
        Get full path to RVC index file.
        Only checks personality directory (index files are model-specific).
        Returns None if index not specified or not found.
        """
        if not self.rvc_index_file:
            return None

        index_path = self.personality_dir / self.rvc_index_file
        if index_path.exists():
            return index_path

        return None

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

    # Get optional RVC settings with defaults
    rvc_enabled = data.get('rvc_enabled', False)
    rvc_model = data.get('rvc_model', None)
    rvc_index_file = data.get('rvc_index_file', None)
    rvc_pitch_shift = data.get('rvc_pitch_shift', 0)
    rvc_index_rate = data.get('rvc_index_rate', 0.5)
    rvc_f0_method = data.get('rvc_f0_method', 'harvest')

    # Validate RVC settings if enabled
    if rvc_enabled:
        if not rvc_model:
            raise ValueError(
                f"personality.yaml in {personality_dir}: 'rvc_model' is required when rvc_enabled=true"
            )

        if not isinstance(rvc_pitch_shift, int) or rvc_pitch_shift < -12 or rvc_pitch_shift > 12:
            raise ValueError(
                f"personality.yaml in {personality_dir}: 'rvc_pitch_shift' must be an integer between -12 and 12"
            )

        if not isinstance(rvc_index_rate, (int, float)) or rvc_index_rate < 0.0 or rvc_index_rate > 1.0:
            raise ValueError(
                f"personality.yaml in {personality_dir}: 'rvc_index_rate' must be between 0.0 and 1.0"
            )

        valid_f0_methods = ['harvest', 'crepe', 'pm', 'dio', 'rmvpe']
        if rvc_f0_method not in valid_f0_methods:
            raise ValueError(
                f"personality.yaml in {personality_dir}: 'rvc_f0_method' must be one of {valid_f0_methods}"
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
        tts_style=tts_style,
        rvc_enabled=rvc_enabled,
        rvc_model=rvc_model,
        rvc_index_file=rvc_index_file,
        rvc_pitch_shift=rvc_pitch_shift,
        rvc_index_rate=rvc_index_rate,
        rvc_f0_method=rvc_f0_method
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
