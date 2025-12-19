"""
Tests for audio device utility functions.
"""

import pytest
from jf_sebastian.utils.audio_device_utils import find_audio_device_by_name


def test_find_input_device_by_exact_name(mock_pyaudio):
    """Test finding input device by exact name match."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "MacBook Air Microphone",
        device_type="input"
    )
    assert device_idx == 0


def test_find_input_device_by_partial_name(mock_pyaudio):
    """Test finding input device by partial name match."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "MacBook Air",
        device_type="input"
    )
    assert device_idx == 0


def test_find_input_device_case_insensitive(mock_pyaudio):
    """Test finding input device with case-insensitive matching."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "macbook air microphone",
        device_type="input"
    )
    assert device_idx == 0


def test_find_output_device_by_name(mock_pyaudio):
    """Test finding output device by name."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "Arsvita",
        device_type="output"
    )
    assert device_idx == 2


def test_find_output_device_exact_match(mock_pyaudio):
    """Test finding output device by exact match."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "MacBook Air Speakers",
        device_type="output"
    )
    assert device_idx == 1


def test_find_device_not_found(mock_pyaudio):
    """Test behavior when device name is not found."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "Nonexistent Device",
        device_type="input"
    )
    assert device_idx is None


def test_find_device_wrong_type(mock_pyaudio):
    """Test that input devices are not returned when searching for output."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "MacBook Air Microphone",
        device_type="output"
    )
    # Should not find microphone when looking for output device
    assert device_idx is None


def test_find_device_empty_name(mock_pyaudio):
    """Test behavior with empty device name."""
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "",
        device_type="input"
    )
    # Empty string matches first available device (partial match behavior)
    assert device_idx == 0


def test_find_device_whitespace_handling(mock_pyaudio):
    """Test whitespace handling in device names."""
    # Leading/trailing whitespace in search string won't match
    device_idx = find_audio_device_by_name(
        mock_pyaudio,
        "  MacBook Air Microphone  ",
        device_type="input"
    )
    # Won't match due to extra spaces
    assert device_idx is None

    # Without extra whitespace, should match
    device_idx2 = find_audio_device_by_name(
        mock_pyaudio,
        "MacBook Air Microphone",
        device_type="input"
    )
    assert device_idx2 == 0
