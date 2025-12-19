"""
Tests for filler phrase system.
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from jf_sebastian.modules.filler_phrases import FillerPhraseManager


def test_filler_manager_initialization(tmp_path):
    """Test FillerPhraseManager initialization."""
    filler_dir = tmp_path / "filler_audio"
    filler_phrases = ["Let me think...", "Hmm...", "Okay..."]
    device_type = "teddy_ruxpin"

    manager = FillerPhraseManager(filler_dir, filler_phrases, device_type)

    assert manager.filler_base_dir == filler_dir
    assert manager.device_type == device_type
    assert manager.filler_dir == filler_dir / device_type
    assert manager.filler_phrases == filler_phrases
    assert manager.filler_files == []  # No files in empty dir


def test_filler_manager_nonexistent_directory(tmp_path, caplog):
    """Test FillerPhraseManager with non-existent directory."""
    import logging

    nonexistent_dir = tmp_path / "does_not_exist"
    filler_phrases = ["Test phrase"]
    device_type = "teddy_ruxpin"

    with caplog.at_level(logging.WARNING):
        manager = FillerPhraseManager(nonexistent_dir, filler_phrases, device_type)

    # Should warn about missing device-specific directory
    assert any("does not exist" in record.message for record in caplog.records)
    assert any("generate_fillers.py" in record.message for record in caplog.records)
    assert any(device_type in record.message for record in caplog.records)


def test_filler_manager_load_files(tmp_path):
    """Test loading filler files from device-specific directory."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Create mock filler files in device-specific directory
    (filler_dir / "filler_01.wav").touch()
    (filler_dir / "filler_02.wav").touch()
    (filler_dir / "filler_03.wav").touch()

    filler_phrases = ["Phrase 1", "Phrase 2", "Phrase 3"]
    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)

    # Should have loaded all filler files
    assert len(manager.filler_files) == 3
    assert all(f.suffix == ".wav" for f in manager.filler_files)
    assert all("filler_" in f.name for f in manager.filler_files)


def test_filler_manager_has_fillers_property(tmp_path):
    """Test has_fillers property."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_phrases = ["Test"]

    # Empty directory (no device subdirectory)
    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    assert manager.has_fillers is False

    # With files in device-specific directory
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_01.wav").touch()
    manager2 = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    assert manager2.has_fillers is True


def test_filler_manager_get_random_filler_no_files(caplog):
    """Test get_random_filler when no files are available."""
    import logging

    manager = FillerPhraseManager(Path("/nonexistent"), ["test"], "teddy_ruxpin")

    with caplog.at_level(logging.WARNING):
        result = manager.get_random_filler()

    assert result is None
    assert any("No filler files available" in record.message for record in caplog.records)


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_success(mock_wavfile, tmp_path):
    """Test successful random filler retrieval."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Create mock filler file
    filler_file = filler_dir / "filler_01.wav"
    filler_file.touch()

    filler_phrases = ["Let me think about that..."]

    # Mock wav file reading
    mock_audio = np.array([0.1, 0.2, 0.3], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    result = manager.get_random_filler()

    # Should return tuple
    assert result is not None
    audio, sample_rate, text = result

    assert sample_rate == 16000
    assert text == "Let me think about that..."
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_int16_conversion(mock_wavfile, tmp_path):
    """Test int16 to float32 conversion."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_01.wav").touch()

    # Mock int16 audio
    mock_audio = np.array([32767, -32768, 0], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, ["test"], device_type)
    result = manager.get_random_filler()

    assert result is not None
    audio, _, _ = result

    # Should be normalized to float32 in range [-1, 1]
    assert audio.dtype == np.float32
    assert np.all(audio >= -1.0)
    assert np.all(audio <= 1.0)

    # Check specific conversions
    assert np.isclose(audio[0], 1.0, atol=0.01)  # 32767 / 32768 ≈ 1.0
    assert np.isclose(audio[1], -1.0, atol=0.01)  # -32768 / 32768 = -1.0


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_int32_conversion(mock_wavfile, tmp_path):
    """Test int32 to float32 conversion."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_01.wav").touch()

    # Mock int32 audio
    mock_audio = np.array([2147483647, -2147483648, 0], dtype=np.int32)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, ["test"], device_type)
    result = manager.get_random_filler()

    assert result is not None
    audio, _, _ = result

    # Should be normalized to float32
    assert audio.dtype == np.float32
    assert np.all(audio >= -1.0)
    assert np.all(audio <= 1.0)


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_multiple_files(mock_wavfile, tmp_path):
    """Test that get_random_filler can return different files."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Create multiple filler files
    (filler_dir / "filler_01.wav").touch()
    (filler_dir / "filler_02.wav").touch()
    (filler_dir / "filler_03.wav").touch()

    filler_phrases = ["Phrase 1", "Phrase 2", "Phrase 3"]

    # Mock wav file reading
    mock_audio = np.array([0.1, 0.2], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)

    # Call multiple times to test randomness
    results = [manager.get_random_filler() for _ in range(10)]

    # All should return valid results
    assert all(r is not None for r in results)

    # Should return one of the phrases
    texts = [r[2] for r in results]
    assert all(t in filler_phrases for t in texts)


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_index_extraction(mock_wavfile, tmp_path):
    """Test extraction of filler index from filename."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    (filler_dir / "filler_05.wav").touch()

    filler_phrases = ["A", "B", "C", "D", "Fifth phrase"]

    mock_audio = np.array([0.1], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    result = manager.get_random_filler()

    assert result is not None
    _, _, text = result

    # filler_05.wav -> index 4 (05 - 1) -> "Fifth phrase"
    assert text == "Fifth phrase"


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_invalid_index(mock_wavfile, tmp_path):
    """Test handling of invalid filler index."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # File index beyond phrases list
    (filler_dir / "filler_99.wav").touch()

    filler_phrases = ["Only one phrase"]

    mock_audio = np.array([0.1], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    result = manager.get_random_filler()

    assert result is not None
    _, _, text = result

    # Should return empty string for out-of-range index
    assert text == ""


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_file_read_error(mock_wavfile, tmp_path, caplog):
    """Test handling of file read errors."""
    import logging

    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_01.wav").touch()

    # Mock wavfile.read to raise an exception
    mock_wavfile.read.side_effect = Exception("Corrupted file")

    manager = FillerPhraseManager(filler_base_dir, ["test"], device_type)

    with caplog.at_level(logging.ERROR):
        result = manager.get_random_filler()

    # Should return None on error
    assert result is None

    # Should log error
    assert any("Error loading filler file" in record.message for record in caplog.records)


@patch('scipy.io.wavfile')
def test_filler_manager_get_random_filler_malformed_filename(mock_wavfile, tmp_path):
    """Test handling of malformed filler filename."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Malformed filename
    (filler_dir / "filler_bad.wav").touch()

    filler_phrases = ["test"]

    mock_audio = np.array([0.1], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    manager = FillerPhraseManager(filler_base_dir, filler_phrases, device_type)
    result = manager.get_random_filler()

    assert result is not None
    _, _, text = result

    # Should return empty string for malformed filename
    assert text == ""


def test_filler_manager_sorted_file_list(tmp_path):
    """Test that filler files are loaded in sorted order."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Create files in non-sorted order
    (filler_dir / "filler_03.wav").touch()
    (filler_dir / "filler_01.wav").touch()
    (filler_dir / "filler_02.wav").touch()

    manager = FillerPhraseManager(filler_base_dir, ["A", "B", "C"], device_type)

    # Should be sorted
    assert len(manager.filler_files) == 3
    assert manager.filler_files[0].name == "filler_01.wav"
    assert manager.filler_files[1].name == "filler_02.wav"
    assert manager.filler_files[2].name == "filler_03.wav"


def test_filler_manager_ignores_non_filler_files(tmp_path):
    """Test that non-filler files are ignored."""
    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)

    # Create filler and non-filler files
    (filler_dir / "filler_01.wav").touch()
    (filler_dir / "other_file.wav").touch()
    (filler_dir / "readme.txt").touch()

    manager = FillerPhraseManager(filler_base_dir, ["test"], device_type)

    # Should only load filler_*.wav files
    assert len(manager.filler_files) == 1
    assert manager.filler_files[0].name == "filler_01.wav"


@patch('scipy.io.wavfile')
def test_filler_manager_logging_on_load(mock_wavfile, tmp_path, caplog):
    """Test that loading filler produces appropriate logs."""
    import logging

    filler_base_dir = tmp_path / "filler_audio"
    device_type = "teddy_ruxpin"
    filler_dir = filler_base_dir / device_type
    filler_dir.mkdir(parents=True)
    (filler_dir / "filler_01.wav").touch()

    mock_audio = np.array([0.1], dtype=np.int16)
    mock_wavfile.read.return_value = (16000, mock_audio)

    with caplog.at_level(logging.INFO):
        manager = FillerPhraseManager(filler_base_dir, ["test"], device_type)
        result = manager.get_random_filler()

    # Should log loading info with device type
    log_messages = [record.message for record in caplog.records]
    assert any("Loaded 1 filler phrases" in msg and device_type in msg for msg in log_messages)
    assert any("Loaded filler: filler_01.wav" in msg for msg in log_messages)
