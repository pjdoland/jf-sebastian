"""
Tests for base personality dataclass and YAML loader.
"""

import pytest
from pathlib import Path
import tempfile
import yaml
from personalities.base import Personality, load_personality_from_yaml, discover_personalities


def test_personality_dataclass():
    """Test Personality dataclass creation."""
    personality_dir = Path("/fake/path/testchar")
    personality = Personality(
        name="TestChar",
        tts_voice="onyx",
        wake_word_model="hey_testchar.onnx",
        system_prompt="You are a test character. You are friendly and helpful.",
        filler_phrases=["Let me think...", "Hmm...", "Okay..."],
        personality_dir=personality_dir
    )

    assert personality.name == "TestChar"
    assert personality.tts_voice == "onyx"
    assert personality.wake_word_model == "hey_testchar.onnx"
    assert "test character" in personality.system_prompt.lower()
    assert len(personality.filler_phrases) == 3
    assert personality.personality_dir == personality_dir


def test_personality_wake_word_model_paths():
    """Test wake_word_model_paths property."""
    personality_dir = Path("/fake/path/testchar")
    personality = Personality(
        name="TestChar",
        tts_voice="onyx",
        wake_word_model="hey_testchar.onnx",
        system_prompt="Test prompt",
        filler_phrases=["Test phrase"],
        personality_dir=personality_dir
    )

    paths = personality.wake_word_model_paths

    # Should be a list of Path objects
    assert isinstance(paths, list)
    assert len(paths) == 1
    assert isinstance(paths[0], Path)
    assert paths[0] == personality_dir / "hey_testchar.onnx"


def test_personality_filler_audio_dir():
    """Test filler_audio_dir property."""
    personality_dir = Path("/fake/path/testchar")
    personality = Personality(
        name="TestChar",
        tts_voice="onyx",
        wake_word_model="hey_testchar.onnx",
        system_prompt="Test prompt",
        filler_phrases=["Test phrase"],
        personality_dir=personality_dir
    )

    filler_dir = personality.filler_audio_dir

    # Should be a Path object
    assert isinstance(filler_dir, Path)
    assert filler_dir == personality_dir / "filler_audio"


def test_personality_get_description():
    """Test get_description method."""
    personality_dir = Path("/fake/path/testchar")
    personality = Personality(
        name="TestChar",
        tts_voice="onyx",
        wake_word_model="hey_testchar.onnx",
        system_prompt="You are a test character. You are friendly and helpful.",
        filler_phrases=["Test phrase"],
        personality_dir=personality_dir
    )

    description = personality.get_description()

    # Should include name
    assert "TestChar" in description

    # Should include first sentence of system prompt
    assert "You are a test character" in description

    # Should be human-readable format
    assert " - " in description


def test_personality_get_description_format():
    """Test that get_description formats correctly."""
    personality_dir = Path("/fake/path/short")
    personality = Personality(
        name="Short",
        tts_voice="onyx",
        wake_word_model="hey_short.onnx",
        system_prompt="Brief prompt without period",
        filler_phrases=["Test phrase"],
        personality_dir=personality_dir
    )

    description = personality.get_description()

    # Should still work even without period
    assert "Short" in description
    assert " - " in description


def test_load_personality_from_yaml():
    """Test loading personality from YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personality_dir = Path(tmpdir) / "testchar"
        personality_dir.mkdir()

        # Create personality.yaml
        yaml_data = {
            "name": "TestChar",
            "tts_voice": "onyx",
            "wake_word_model": "hey_testchar.onnx",
            "system_prompt": "You are a test character. You are friendly and helpful.",
            "filler_phrases": ["Let me think...", "Hmm...", "Okay..."]
        }

        yaml_path = personality_dir / "personality.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f)

        # Load personality
        personality = load_personality_from_yaml(personality_dir)

        assert personality.name == "TestChar"
        assert personality.tts_voice == "onyx"
        assert personality.wake_word_model == "hey_testchar.onnx"
        assert "test character" in personality.system_prompt.lower()
        assert len(personality.filler_phrases) == 3
        assert personality.personality_dir == personality_dir


def test_load_personality_missing_file():
    """Test error when personality.yaml doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personality_dir = Path(tmpdir) / "testchar"
        personality_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            load_personality_from_yaml(personality_dir)


def test_load_personality_missing_required_field():
    """Test error when required field is missing from YAML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personality_dir = Path(tmpdir) / "testchar"
        personality_dir.mkdir()

        # Create incomplete YAML (missing system_prompt)
        yaml_data = {
            "name": "TestChar",
            "tts_voice": "onyx",
            "wake_word_model": "hey_testchar.onnx",
            "filler_phrases": ["Test phrase"]
        }

        yaml_path = personality_dir / "personality.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f)

        with pytest.raises(ValueError, match="missing required fields"):
            load_personality_from_yaml(personality_dir)


def test_load_personality_invalid_filler_phrases():
    """Test error when filler_phrases is not a list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personality_dir = Path(tmpdir) / "testchar"
        personality_dir.mkdir()

        # Create YAML with invalid filler_phrases
        yaml_data = {
            "name": "TestChar",
            "tts_voice": "onyx",
            "wake_word_model": "hey_testchar.onnx",
            "system_prompt": "Test prompt",
            "filler_phrases": "Not a list"  # Should be a list
        }

        yaml_path = personality_dir / "personality.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f)

        with pytest.raises(ValueError, match="must be a list"):
            load_personality_from_yaml(personality_dir)


def test_discover_personalities():
    """Test auto-discovery of personalities."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personalities_root = Path(tmpdir)

        # Create two personality directories
        for name in ["testchar1", "testchar2"]:
            personality_dir = personalities_root / name
            personality_dir.mkdir()

            yaml_data = {
                "name": name.title(),
                "tts_voice": "onyx",
                "wake_word_model": f"hey_{name}.onnx",
                "system_prompt": f"You are {name}",
                "filler_phrases": ["Test phrase"]
            }

            with open(personality_dir / "personality.yaml", 'w') as f:
                yaml.dump(yaml_data, f)

        # Create a directory without personality.yaml (should be ignored)
        (personalities_root / "not_a_personality").mkdir()

        # Discover personalities
        personalities = discover_personalities(personalities_root)

        assert len(personalities) == 2
        assert "testchar1" in personalities
        assert "testchar2" in personalities
        assert "not_a_personality" not in personalities
        assert isinstance(personalities["testchar1"], Path)


def test_discover_personalities_empty_dir():
    """Test discovery in empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        personalities = discover_personalities(Path(tmpdir))
        assert personalities == {}


def test_discover_personalities_nonexistent_dir():
    """Test discovery in nonexistent directory."""
    personalities = discover_personalities(Path("/nonexistent/path"))
    assert personalities == {}


def test_personality_get_description_with_multisentence_prompt():
    """Test get_description with multi-sentence system prompt."""
    personality_dir = Path("/fake/path/multi")
    personality = Personality(
        name="MultiSentence",
        tts_voice="onyx",
        wake_word_model="hey_multi.onnx",
        system_prompt="First sentence here. Second sentence. Third sentence.",
        filler_phrases=["Test phrase"],
        personality_dir=personality_dir
    )

    description = personality.get_description()

    # Should only include first sentence
    assert "First sentence here" in description
    assert "Second sentence" not in description
    assert "Third sentence" not in description
