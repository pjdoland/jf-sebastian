"""
Base personality class for animatronic characters.
Defines the interface that all personalities must implement.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class Personality(ABC):
    """
    Base class for animatronic personalities.
    Each personality defines its own character traits, wake word, and filler phrases.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Character name (e.g., 'Johnny', 'Rich')"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt that defines the character's personality for the LLM"""
        pass

    @property
    @abstractmethod
    def wake_word_model_paths(self) -> List[Path]:
        """List of paths to custom wake word model files (.onnx or .tflite)"""
        pass

    @property
    @abstractmethod
    def filler_phrases(self) -> List[str]:
        """List of filler phrases for low-latency responses"""
        pass

    @property
    @abstractmethod
    def tts_voice(self) -> str:
        """OpenAI TTS voice ID (e.g., 'onyx', 'echo', 'fable')"""
        pass

    @property
    def filler_audio_dir(self) -> Path:
        """Directory containing pre-generated filler audio files"""
        personality_dir = Path(__file__).parent / self.name.lower()
        return personality_dir / "filler_audio"

    def get_description(self) -> str:
        """Get a human-readable description of this personality"""
        return f"{self.name} - {self.system_prompt.split('.')[0]}"
