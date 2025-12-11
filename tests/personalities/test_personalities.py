"""
Tests for personality system.
"""

import pytest
from pathlib import Path
from personalities import get_personality, list_personalities
from personalities.base import Personality


def test_get_personality_johnny():
    """Test loading Johnny personality."""
    personality = get_personality("johnny")

    assert isinstance(personality, Personality)
    assert personality.name == "Johnny"
    assert personality.tts_voice == "onyx"
    assert len(personality.filler_phrases) > 0
    assert personality.system_prompt != ""


def test_get_personality_mr_lincoln():
    """Test loading Mr. Lincoln personality."""
    personality = get_personality("mr_lincoln")

    assert isinstance(personality, Personality)
    assert personality.name == "Mr. Lincoln"
    assert personality.tts_voice == "echo"
    assert len(personality.filler_phrases) > 0
    assert personality.system_prompt != ""


def test_get_personality_leopold():
    """Test loading Leopold personality."""
    personality = get_personality("leopold")

    assert isinstance(personality, Personality)
    assert personality.name == "Leopold"
    assert personality.tts_voice == "onyx"
    assert len(personality.filler_phrases) > 0
    assert personality.system_prompt != ""


def test_get_personality_case_insensitive():
    """Test that personality loading is case-insensitive."""
    personality1 = get_personality("JOHNNY")
    personality2 = get_personality("Johnny")
    personality3 = get_personality("johnny")

    assert isinstance(personality1, Personality)
    assert isinstance(personality2, Personality)
    assert isinstance(personality3, Personality)
    assert personality1.name == personality2.name == personality3.name == "Johnny"


def test_get_personality_invalid():
    """Test error handling for invalid personality name."""
    with pytest.raises(ValueError, match="Unknown personality"):
        get_personality("invalid_personality")


def test_johnny_personality_properties():
    """Test Johnny personality has all required properties."""
    johnny = get_personality("johnny")

    # Check required properties
    assert johnny.name == "Johnny"
    assert isinstance(johnny.system_prompt, str)
    assert len(johnny.system_prompt) > 100  # Should be substantial
    assert isinstance(johnny.wake_word_model_paths, list)
    assert all(isinstance(p, Path) for p in johnny.wake_word_model_paths)
    assert isinstance(johnny.tts_voice, str)
    assert isinstance(johnny.filler_phrases, list)
    assert len(johnny.filler_phrases) > 0
    assert isinstance(johnny.filler_audio_dir, Path)


def test_mr_lincoln_personality_properties():
    """Test Mr. Lincoln personality has all required properties."""
    mr_lincoln = get_personality("mr_lincoln")

    # Check required properties
    assert mr_lincoln.name == "Mr. Lincoln"
    assert isinstance(mr_lincoln.system_prompt, str)
    assert len(mr_lincoln.system_prompt) > 100  # Should be substantial
    assert isinstance(mr_lincoln.wake_word_model_paths, list)
    assert all(isinstance(p, Path) for p in mr_lincoln.wake_word_model_paths)
    assert isinstance(mr_lincoln.tts_voice, str)
    assert isinstance(mr_lincoln.filler_phrases, list)
    assert len(mr_lincoln.filler_phrases) > 0
    assert isinstance(mr_lincoln.filler_audio_dir, Path)


def test_johnny_filler_phrases_valid():
    """Test that Johnny's filler phrases are properly formatted."""
    johnny = get_personality("johnny")

    for phrase in johnny.filler_phrases:
        # Should be non-empty strings
        assert isinstance(phrase, str)
        assert len(phrase) > 0
        assert phrase.strip() == phrase  # No leading/trailing whitespace


def test_leopold_filler_phrases_valid():
    """Test that Leopold's filler phrases are properly formatted."""
    leopold = get_personality("leopold")

    for phrase in leopold.filler_phrases:
        # Should be non-empty strings
        assert isinstance(phrase, str)
        assert len(phrase) > 0
        assert phrase.strip() == phrase  # No leading/trailing whitespace


def test_johnny_system_prompt_content():
    """Test Johnny's system prompt contains key elements."""
    johnny = get_personality("johnny")
    prompt = johnny.system_prompt.lower()

    # Should reference tiki bar theme
    assert "tiki" in prompt or "bar" in prompt


def test_mr_lincoln_system_prompt_content():
    """Test Mr. Lincoln's system prompt contains key elements."""
    mr_lincoln = get_personality("mr_lincoln")
    prompt = mr_lincoln.system_prompt.lower()

    # Should reference Lincoln or presidential theme
    assert "lincoln" in prompt or "president" in prompt


def test_personality_filler_audio_dir_structure():
    """Test that filler audio directory paths are correctly structured."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Should point to personality-specific directories
    assert "johnny" in str(johnny.filler_audio_dir).lower()
    assert "leopold" in str(leopold.filler_audio_dir).lower()

    # Paths should be different
    assert johnny.filler_audio_dir != leopold.filler_audio_dir


def test_personality_has_filler_phrases():
    """Test that personalities have filler phrases defined."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Both should have filler phrases defined
    assert len(johnny.filler_phrases) > 0
    assert len(leopold.filler_phrases) > 0


def test_personality_base_class():
    """Test that all personalities are Personality instances."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    assert isinstance(johnny, Personality)
    assert isinstance(leopold, Personality)


def test_personality_filler_phrase_count():
    """Test that personalities have sufficient filler phrases."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Should have at least 10 filler phrases for variety
    assert len(johnny.filler_phrases) >= 10
    assert len(leopold.filler_phrases) >= 10


def test_personality_filler_phrases_unique():
    """Test that filler phrases are unique (no duplicates)."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    johnny_set = set(johnny.filler_phrases)
    leopold_set = set(leopold.filler_phrases)

    # All phrases should be unique
    assert len(johnny_set) == len(johnny.filler_phrases)
    assert len(leopold_set) == len(leopold.filler_phrases)


def test_personality_filler_phrases_substantial():
    """Test that filler phrases are substantial (not too short)."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Fillers should be at least 20 characters (substantial pauses)
    for phrase in johnny.filler_phrases:
        assert len(phrase) >= 20, f"Johnny phrase too short: {phrase}"

    for phrase in leopold.filler_phrases:
        assert len(phrase) >= 20, f"Leopold phrase too short: {phrase}"


def test_johnny_voice_appropriate():
    """Test Johnny uses appropriate TTS voice."""
    johnny = get_personality("johnny")

    # Johnny should use a male voice
    # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
    assert johnny.tts_voice in ["onyx", "echo", "fable", "alloy"]


def test_leopold_voice_appropriate():
    """Test Leopold uses appropriate TTS voice."""
    leopold = get_personality("leopold")

    # Leopold should use a voice fitting his character
    assert leopold.tts_voice in ["echo", "onyx", "fable", "alloy"]


def test_personality_wake_word_model_paths_exist():
    """Test that wake word model paths are defined."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Should have lists of Path objects
    assert isinstance(johnny.wake_word_model_paths, list)
    assert isinstance(leopold.wake_word_model_paths, list)
    assert all(isinstance(p, Path) for p in johnny.wake_word_model_paths)
    assert all(isinstance(p, Path) for p in leopold.wake_word_model_paths)


def test_personality_wake_word_models_have_onnx_extension():
    """Test that wake word models have .onnx extension."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    for path in johnny.wake_word_model_paths:
        assert path.suffix == ".onnx"
    for path in leopold.wake_word_model_paths:
        assert path.suffix == ".onnx"


def test_get_personality_caching():
    """Test that get_personality caches results."""
    p1 = get_personality("johnny")
    p2 = get_personality("johnny")

    # Should return the same cached instance
    assert p1 is p2


def test_personality_system_prompts_different():
    """Test that different personalities have different system prompts."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Should have distinct personalities
    assert johnny.system_prompt != leopold.system_prompt


def test_personality_filler_phrases_different():
    """Test that different personalities have different filler phrases."""
    johnny = get_personality("johnny")
    leopold = get_personality("leopold")

    # Should have mostly different phrases
    johnny_set = set(johnny.filler_phrases)
    leopold_set = set(leopold.filler_phrases)

    # Overlap should be minimal (less than 10%)
    overlap = johnny_set.intersection(leopold_set)
    assert len(overlap) < len(johnny.filler_phrases) * 0.1


def test_list_personalities():
    """Test that list_personalities returns available personalities."""
    personalities = list_personalities()

    assert isinstance(personalities, list)
    assert len(personalities) >= 3  # At least johnny, mr_lincoln, leopold
    assert "johnny" in personalities
    assert "mr_lincoln" in personalities
    assert "leopold" in personalities
