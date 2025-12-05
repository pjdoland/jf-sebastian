"""
Tests for base personality class.
"""

import pytest
from pathlib import Path
from teddy_ruxpin.personalities.base import Personality


# Create a concrete implementation for testing
class TestPersonality(Personality):
    """Test implementation of Personality for testing base class."""

    @property
    def name(self) -> str:
        return "TestChar"

    @property
    def system_prompt(self) -> str:
        return "You are a test character. You are friendly and helpful."

    @property
    def wake_word_path(self) -> Path:
        return Path("/fake/path/test.ppn")

    @property
    def filler_phrases(self) -> list:
        return ["Let me think...", "Hmm...", "Okay..."]

    @property
    def tts_voice(self) -> str:
        return "onyx"


def test_personality_abstract_class():
    """Test that Personality is an abstract class."""
    # Should not be able to instantiate directly
    with pytest.raises(TypeError):
        Personality()


def test_personality_concrete_implementation():
    """Test that concrete implementation works."""
    personality = TestPersonality()

    assert personality.name == "TestChar"
    assert "test character" in personality.system_prompt.lower()
    assert personality.wake_word_path == Path("/fake/path/test.ppn")
    assert len(personality.filler_phrases) == 3
    assert personality.tts_voice == "onyx"


def test_personality_filler_audio_dir():
    """Test filler_audio_dir property."""
    personality = TestPersonality()

    filler_dir = personality.filler_audio_dir

    # Should be a Path object
    assert isinstance(filler_dir, Path)

    # Should include personality name (lowercase)
    assert "testchar" in str(filler_dir).lower()

    # Should end with filler_audio
    assert filler_dir.name == "filler_audio"


def test_personality_get_description():
    """Test get_description method."""
    personality = TestPersonality()

    description = personality.get_description()

    # Should include name
    assert personality.name in description

    # Should include first sentence of system prompt
    assert "You are a test character" in description

    # Should be human-readable format
    assert " - " in description


def test_personality_get_description_format():
    """Test that get_description formats correctly."""
    class ShortPromptPersonality(TestPersonality):
        @property
        def name(self) -> str:
            return "Short"

        @property
        def system_prompt(self) -> str:
            return "Brief prompt without period"

    personality = ShortPromptPersonality()
    description = personality.get_description()

    # Should still work even without period
    assert "Short" in description
    assert " - " in description


def test_personality_abstract_methods_required():
    """Test that all abstract methods must be implemented."""

    # Missing name property
    class MissingNamePersonality(Personality):
        @property
        def system_prompt(self) -> str:
            return "Test"

        @property
        def wake_word_path(self) -> Path:
            return Path("/test")

        @property
        def filler_phrases(self) -> list:
            return []

        @property
        def tts_voice(self) -> str:
            return "onyx"

    # Should raise TypeError for missing abstract method
    with pytest.raises(TypeError):
        MissingNamePersonality()


def test_personality_filler_audio_dir_path_structure():
    """Test that filler_audio_dir constructs correct path structure."""

    class CustomNamePersonality(TestPersonality):
        @property
        def name(self) -> str:
            return "CustomName"

    personality = CustomNamePersonality()
    filler_dir = personality.filler_audio_dir

    # Path should include personalities dir
    path_parts = filler_dir.parts

    # Should have customname directory
    assert any("customname" in part.lower() for part in path_parts)

    # Should end with filler_audio
    assert path_parts[-1] == "filler_audio"


def test_personality_properties_are_properties():
    """Test that abstract members are defined as properties."""
    personality = TestPersonality()

    # All required attributes should be accessible without calling
    assert isinstance(personality.name, str)
    assert isinstance(personality.system_prompt, str)
    assert isinstance(personality.wake_word_path, Path)
    assert isinstance(personality.filler_phrases, list)
    assert isinstance(personality.tts_voice, str)
    assert isinstance(personality.filler_audio_dir, Path)


def test_personality_get_description_with_multisentence_prompt():
    """Test get_description with multi-sentence system prompt."""

    class MultiSentencePersonality(TestPersonality):
        @property
        def name(self) -> str:
            return "MultiSentence"

        @property
        def system_prompt(self) -> str:
            return "First sentence here. Second sentence. Third sentence."

    personality = MultiSentencePersonality()
    description = personality.get_description()

    # Should only include first sentence
    assert "First sentence here" in description
    assert "Second sentence" not in description
    assert "Third sentence" not in description


def test_personality_name_casing_in_filler_audio_dir():
    """Test that filler_audio_dir converts name to lowercase."""

    class MixedCasePersonality(TestPersonality):
        @property
        def name(self) -> str:
            return "MixedCaseName"

    personality = MixedCasePersonality()
    filler_dir = personality.filler_audio_dir

    # Should convert to lowercase
    assert "mixedcasename" in str(filler_dir).lower()


def test_personality_filler_phrases_is_list():
    """Test that filler_phrases returns a list."""
    personality = TestPersonality()

    phrases = personality.filler_phrases

    assert isinstance(phrases, list)
    assert all(isinstance(phrase, str) for phrase in phrases)


def test_personality_wake_word_path_is_path():
    """Test that wake_word_path returns a Path object."""
    personality = TestPersonality()

    wake_path = personality.wake_word_path

    assert isinstance(wake_path, Path)
