"""
Tests for filler phrase management.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from teddy_ruxpin.modules.filler_phrases import FillerManager


def test_filler_manager_initialization_with_fillers(temp_audio_dir, mock_personality):
    """Test FillerManager initialization when filler files exist."""
    # Create fake filler files
    mock_personality.filler_audio_dir = temp_audio_dir
    for i in range(1, 6):
        (temp_audio_dir / f"filler_{i:02d}.wav").touch()

    mock_personality.filler_phrases = [
        "Phrase 1",
        "Phrase 2",
        "Phrase 3",
        "Phrase 4",
        "Phrase 5"
    ]

    manager = FillerManager(mock_personality)

    assert manager.has_fillers is True
    assert len(manager._filler_files) == 5
    assert len(manager._filler_texts) == 5


def test_filler_manager_initialization_no_files(temp_audio_dir, mock_personality):
    """Test FillerManager initialization when no filler files exist."""
    mock_personality.filler_audio_dir = temp_audio_dir
    mock_personality.filler_phrases = ["Phrase 1", "Phrase 2"]

    manager = FillerManager(mock_personality)

    assert manager.has_fillers is False
    assert len(manager._filler_files) == 0


def test_filler_manager_initialization_mismatched_counts(temp_audio_dir, mock_personality):
    """Test FillerManager when file count doesn't match phrase count."""
    mock_personality.filler_audio_dir = temp_audio_dir

    # Create 3 files
    for i in range(1, 4):
        (temp_audio_dir / f"filler_{i:02d}.wav").touch()

    # But provide 5 phrases
    mock_personality.filler_phrases = [
        "Phrase 1",
        "Phrase 2",
        "Phrase 3",
        "Phrase 4",
        "Phrase 5"
    ]

    manager = FillerManager(mock_personality)

    # Should only use the minimum count
    assert len(manager._filler_files) == 3
    assert len(manager._filler_texts) == 3


def test_get_random_filler(temp_audio_dir, mock_personality):
    """Test getting a random filler phrase."""
    mock_personality.filler_audio_dir = temp_audio_dir
    for i in range(1, 4):
        (temp_audio_dir / f"filler_{i:02d}.wav").touch()

    mock_personality.filler_phrases = ["Phrase 1", "Phrase 2", "Phrase 3"]

    manager = FillerManager(mock_personality)
    result = manager.get_random_filler()

    assert result is not None
    audio_path, sample_rate, text = result

    # Check returned values
    assert isinstance(audio_path, Path)
    assert audio_path.exists()
    assert sample_rate == 16000
    assert text in mock_personality.filler_phrases


def test_get_random_filler_no_fillers(mock_personality):
    """Test get_random_filler when no fillers available."""
    mock_personality.filler_audio_dir = Path("/nonexistent")
    mock_personality.filler_phrases = []

    manager = FillerManager(mock_personality)
    result = manager.get_random_filler()

    assert result is None


def test_get_random_filler_distribution(temp_audio_dir, mock_personality):
    """Test that random filler selection has reasonable distribution."""
    mock_personality.filler_audio_dir = temp_audio_dir
    num_fillers = 5
    for i in range(1, num_fillers + 1):
        (temp_audio_dir / f"filler_{i:02d}.wav").touch()

    mock_personality.filler_phrases = [f"Phrase {i}" for i in range(1, num_fillers + 1)]

    manager = FillerManager(mock_personality)

    # Get 50 random fillers
    selected_texts = []
    for _ in range(50):
        result = manager.get_random_filler()
        if result:
            selected_texts.append(result[2])

    # Should have selected from all available fillers (with high probability)
    unique_selections = set(selected_texts)
    assert len(unique_selections) >= 3  # Should see at least 3 different fillers


def test_filler_manager_loads_correct_files(temp_audio_dir, mock_personality):
    """Test that FillerManager loads files in correct order."""
    mock_personality.filler_audio_dir = temp_audio_dir

    # Create files in non-sequential order
    (temp_audio_dir / "filler_03.wav").touch()
    (temp_audio_dir / "filler_01.wav").touch()
    (temp_audio_dir / "filler_02.wav").touch()

    mock_personality.filler_phrases = ["First", "Second", "Third"]

    manager = FillerManager(mock_personality)

    # Files should be sorted
    assert manager._filler_files[0].name == "filler_01.wav"
    assert manager._filler_files[1].name == "filler_02.wav"
    assert manager._filler_files[2].name == "filler_03.wav"

    # Texts should match file order
    assert manager._filler_texts[0] == "First"
    assert manager._filler_texts[1] == "Second"
    assert manager._filler_texts[2] == "Third"


def test_filler_manager_ignores_non_filler_files(temp_audio_dir, mock_personality):
    """Test that FillerManager ignores non-filler WAV files."""
    mock_personality.filler_audio_dir = temp_audio_dir

    # Create mix of filler and non-filler files
    (temp_audio_dir / "filler_01.wav").touch()
    (temp_audio_dir / "filler_02.wav").touch()
    (temp_audio_dir / "random_audio.wav").touch()
    (temp_audio_dir / "test.wav").touch()

    mock_personality.filler_phrases = ["Phrase 1", "Phrase 2"]

    manager = FillerManager(mock_personality)

    # Should only load filler_XX.wav files
    assert len(manager._filler_files) == 2
    assert all("filler_" in f.name for f in manager._filler_files)


def test_filler_manager_empty_directory(temp_audio_dir, mock_personality):
    """Test FillerManager with empty filler directory."""
    mock_personality.filler_audio_dir = temp_audio_dir
    mock_personality.filler_phrases = ["Phrase 1", "Phrase 2"]

    manager = FillerManager(mock_personality)

    assert manager.has_fillers is False
    assert manager.get_random_filler() is None


def test_filler_manager_nonexistent_directory(mock_personality):
    """Test FillerManager with non-existent directory."""
    mock_personality.filler_audio_dir = Path("/totally/fake/path")
    mock_personality.filler_phrases = ["Phrase 1"]

    manager = FillerManager(mock_personality)

    assert manager.has_fillers is False


def test_filler_manager_sample_rate(temp_audio_dir, mock_personality):
    """Test that FillerManager returns correct sample rate."""
    mock_personality.filler_audio_dir = temp_audio_dir
    (temp_audio_dir / "filler_01.wav").touch()
    mock_personality.filler_phrases = ["Test"]

    manager = FillerManager(mock_personality)
    result = manager.get_random_filler()

    assert result is not None
    _, sample_rate, _ = result
    assert sample_rate == 16000  # Default sample rate


def test_filler_manager_personality_without_fillers(mock_personality):
    """Test FillerManager with personality that has no filler phrases."""
    mock_personality.filler_audio_dir = Path("/fake/path")
    mock_personality.filler_phrases = []

    manager = FillerManager(mock_personality)

    assert manager.has_fillers is False
    assert len(manager._filler_files) == 0
    assert len(manager._filler_texts) == 0
