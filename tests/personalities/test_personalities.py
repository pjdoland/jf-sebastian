"""
Tests for personality system.
"""

import pytest
from pathlib import Path
from teddy_ruxpin.personalities import get_personality
from teddy_ruxpin.personalities.base import Personality
from teddy_ruxpin.personalities.johnny.personality import JohnnyPersonality
from teddy_ruxpin.personalities.rich.personality import RichPersonality


def test_get_personality_johnny():
    """Test loading Johnny personality."""
    personality = get_personality("johnny")

    assert isinstance(personality, JohnnyPersonality)
    assert personality.name == "Johnny"
    assert personality.tts_voice == "onyx"
    assert len(personality.filler_phrases) > 0
    assert personality.system_prompt != ""


def test_get_personality_rich():
    """Test loading Rich personality."""
    personality = get_personality("rich")

    assert isinstance(personality, RichPersonality)
    assert personality.name == "Rich"
    assert personality.tts_voice == "echo"
    assert len(personality.filler_phrases) > 0
    assert personality.system_prompt != ""


def test_get_personality_case_insensitive():
    """Test that personality loading is case-insensitive."""
    personality1 = get_personality("JOHNNY")
    personality2 = get_personality("Johnny")
    personality3 = get_personality("johnny")

    assert isinstance(personality1, JohnnyPersonality)
    assert isinstance(personality2, JohnnyPersonality)
    assert isinstance(personality3, JohnnyPersonality)


def test_get_personality_invalid():
    """Test error handling for invalid personality name."""
    with pytest.raises(ValueError, match="Unknown personality"):
        get_personality("invalid_personality")


def test_johnny_personality_properties():
    """Test Johnny personality has all required properties."""
    johnny = JohnnyPersonality()

    # Check required properties
    assert johnny.name == "Johnny"
    assert isinstance(johnny.system_prompt, str)
    assert len(johnny.system_prompt) > 100  # Should be substantial
    assert isinstance(johnny.wake_word_path, Path)
    assert isinstance(johnny.tts_voice, str)
    assert isinstance(johnny.filler_phrases, list)
    assert len(johnny.filler_phrases) > 0
    assert isinstance(johnny.filler_audio_dir, Path)


def test_rich_personality_properties():
    """Test Rich personality has all required properties."""
    rich = RichPersonality()

    # Check required properties
    assert rich.name == "Rich"
    assert isinstance(rich.system_prompt, str)
    assert len(rich.system_prompt) > 100  # Should be substantial
    assert isinstance(rich.wake_word_path, Path)
    assert isinstance(rich.tts_voice, str)
    assert isinstance(rich.filler_phrases, list)
    assert len(rich.filler_phrases) > 0
    assert isinstance(rich.filler_audio_dir, Path)


def test_johnny_filler_phrases_valid():
    """Test that Johnny's filler phrases are properly formatted."""
    johnny = JohnnyPersonality()

    for phrase in johnny.filler_phrases:
        # Should be non-empty strings
        assert isinstance(phrase, str)
        assert len(phrase) > 0
        assert phrase.strip() == phrase  # No leading/trailing whitespace


def test_rich_filler_phrases_valid():
    """Test that Rich's filler phrases are properly formatted."""
    rich = RichPersonality()

    for phrase in rich.filler_phrases:
        # Should be non-empty strings
        assert isinstance(phrase, str)
        assert len(phrase) > 0
        assert phrase.strip() == phrase  # No leading/trailing whitespace


def test_johnny_system_prompt_content():
    """Test Johnny's system prompt contains key elements."""
    johnny = JohnnyPersonality()
    prompt = johnny.system_prompt.lower()

    # Should reference tiki bar theme
    assert "tiki" in prompt or "bar" in prompt
    # Should reference animatronic nature
    assert "animatronic" in prompt or "teddy ruxpin" in prompt


def test_rich_system_prompt_content():
    """Test Rich's system prompt contains key elements."""
    rich = RichPersonality()
    prompt = rich.system_prompt.lower()

    # Should reference banking/financial theme
    assert "bank" in prompt or "ceo" in prompt
    # Should reference animatronic nature
    assert "animatronic" in prompt


def test_personality_filler_audio_dir_structure():
    """Test that filler audio directory paths are correctly structured."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Should point to personality-specific directories
    assert "johnny" in str(johnny.filler_audio_dir).lower()
    assert "rich" in str(rich.filler_audio_dir).lower()

    # Paths should be different
    assert johnny.filler_audio_dir != rich.filler_audio_dir


def test_personality_has_filler_phrases():
    """Test that personalities have filler phrases defined."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Both should have filler phrases defined
    assert len(johnny.filler_phrases) > 0
    assert len(rich.filler_phrases) > 0


def test_personality_base_class():
    """Test that both personalities inherit from Personality base class."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    assert isinstance(johnny, Personality)
    assert isinstance(rich, Personality)


def test_personality_filler_phrase_count():
    """Test that personalities have sufficient filler phrases."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Should have at least 10 filler phrases for variety
    assert len(johnny.filler_phrases) >= 10
    assert len(rich.filler_phrases) >= 10


def test_personality_filler_phrases_unique():
    """Test that filler phrases are unique (no duplicates)."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    johnny_set = set(johnny.filler_phrases)
    rich_set = set(rich.filler_phrases)

    # All phrases should be unique
    assert len(johnny_set) == len(johnny.filler_phrases)
    assert len(rich_set) == len(rich.filler_phrases)


def test_personality_filler_phrases_substantial():
    """Test that filler phrases are substantial (not too short)."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Fillers should be at least 20 characters (substantial pauses)
    for phrase in johnny.filler_phrases:
        assert len(phrase) >= 20, f"Johnny phrase too short: {phrase}"

    for phrase in rich.filler_phrases:
        assert len(phrase) >= 20, f"Rich phrase too short: {phrase}"


def test_johnny_voice_appropriate():
    """Test Johnny uses appropriate TTS voice."""
    johnny = JohnnyPersonality()

    # Johnny should use a male voice
    # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
    assert johnny.tts_voice in ["onyx", "echo", "fable", "alloy"]


def test_rich_voice_appropriate():
    """Test Rich uses appropriate TTS voice."""
    rich = RichPersonality()

    # Rich should use professional male voice
    assert rich.tts_voice in ["echo", "onyx", "fable", "alloy"]


def test_personality_wake_word_paths_exist():
    """Test that wake word file paths are defined."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Paths should be Path objects
    assert isinstance(johnny.wake_word_path, Path)
    assert isinstance(rich.wake_word_path, Path)

    # Paths should be different
    assert johnny.wake_word_path != rich.wake_word_path


def test_personality_wake_word_paths_have_ppn_extension():
    """Test that wake word files have .ppn extension."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    assert johnny.wake_word_path.suffix == ".ppn"
    assert rich.wake_word_path.suffix == ".ppn"


def test_get_personality_returns_same_class():
    """Test that get_personality returns consistent class instances."""
    p1 = get_personality("johnny")
    p2 = get_personality("johnny")

    # Should be same class
    assert type(p1) == type(p2)

    # But different instances
    assert p1 is not p2


def test_personality_system_prompts_different():
    """Test that different personalities have different system prompts."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Should have distinct personalities
    assert johnny.system_prompt != rich.system_prompt


def test_personality_filler_phrases_different():
    """Test that different personalities have different filler phrases."""
    johnny = JohnnyPersonality()
    rich = RichPersonality()

    # Should have mostly different phrases
    johnny_set = set(johnny.filler_phrases)
    rich_set = set(rich.filler_phrases)

    # Overlap should be minimal (less than 10%)
    overlap = johnny_set.intersection(rich_set)
    assert len(overlap) < len(johnny.filler_phrases) * 0.1
