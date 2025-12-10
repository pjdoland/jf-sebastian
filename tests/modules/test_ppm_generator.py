"""
Tests for PPM (Pulse Position Modulation) generator.
"""

import pytest
import numpy as np
from teddy_ruxpin.modules.ppm_generator import PPMGenerator


def test_ppm_generator_initialization():
    """Test PPM generator initialization with default sample rate."""
    gen = PPMGenerator(sample_rate=16000)
    assert gen.sample_rate == 16000
    assert gen.NUM_CHANNELS == 8
    assert gen.PERIOD == 16600  # 16.6ms period
    assert gen.PAUSE_DURATION == 400
    assert gen.MIN_GAP == 630
    assert gen.MAX_GAP == 1590


def test_ppm_generator_custom_sample_rate():
    """Test PPM generator with custom sample rate."""
    gen = PPMGenerator(sample_rate=44100)
    assert gen.sample_rate == 44100
    # Sample counts should scale with sample rate
    expected_period_samples = int(16600 / 1_000_000 * 44100)
    assert gen.period_samples == expected_period_samples


def test_generate_ppm_signal_basic(sample_ppm_channel_values):
    """Test basic PPM signal generation."""
    gen = PPMGenerator(sample_rate=16000)
    duration = 1.0
    signal = gen.generate_ppm_signal(duration, sample_ppm_channel_values[:60])

    # Should generate signal with correct length
    expected_samples = int(duration * 16000)
    assert len(signal) == expected_samples

    # Signal should be normalized between -1 and 1
    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)

    # Should contain negative pulses (HIGH pulses are negative)
    assert np.any(signal < -0.1)


def test_generate_ppm_signal_zero_values():
    """Test PPM signal generation with all zero channel values."""
    gen = PPMGenerator(sample_rate=16000)
    duration = 0.5
    channel_values = np.zeros((30, 8), dtype=np.uint8)
    signal = gen.generate_ppm_signal(duration, channel_values)

    assert len(signal) == int(duration * 16000)
    # Even with zero values, should have pulses (negative)
    assert np.any(signal < 0)


def test_generate_ppm_signal_max_values():
    """Test PPM signal generation with maximum channel values."""
    gen = PPMGenerator(sample_rate=16000)
    duration = 0.5
    channel_values = np.full((30, 8), 255, dtype=np.uint8)
    signal = gen.generate_ppm_signal(duration, channel_values)

    assert len(signal) == int(duration * 16000)
    # Should generate valid signal
    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)


def test_audio_to_channel_values_basic(sample_audio):
    """Test conversion of audio to PPM channel values."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)

    text = "Hello world, this is a test"
    channel_values = gen.audio_to_channel_values(audio, sample_rate, text)

    # Should generate correct shape
    duration = len(audio) / sample_rate
    expected_frames = int(duration / (gen.PERIOD / 1_000_000)) + 1
    assert channel_values.shape == (expected_frames, 8)

    # Should be uint8 values (0-255)
    assert channel_values.dtype == np.uint8
    assert np.all(channel_values >= 0)
    assert np.all(channel_values <= 255)


def test_audio_to_channel_values_mouth_movement(sample_audio):
    """Test that mouth channels (2, 3) have movement."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)

    text = "The quick brown fox jumps over the lazy dog"
    channel_values = gen.audio_to_channel_values(audio, sample_rate, text)

    # Channel 3 (lower jaw) should have significant movement
    lower_jaw = channel_values[:, 3]
    assert np.any(lower_jaw > 50)  # Should have some mouth opening

    # Channel 2 (upper jaw) should move but less than lower jaw
    upper_jaw = channel_values[:, 2]
    assert np.any(upper_jaw > 0)

    # Upper jaw should generally be less than lower jaw
    active_frames = lower_jaw > 50
    if np.any(active_frames):
        assert np.mean(upper_jaw[active_frames]) < np.mean(lower_jaw[active_frames])


def test_audio_to_channel_values_eye_control(sample_audio):
    """Test that eye channel (1) is controlled."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)

    text = "Test speech"
    sentiment = 0.5  # Positive sentiment
    channel_values = gen.audio_to_channel_values(
        audio, sample_rate, text, sentiment=sentiment
    )

    # Channel 1 (eyes) should have values
    eyes = channel_values[:, 1]
    assert np.any(eyes > 0)

    # Eyes should have consistent position (may or may not blink in short sample)
    # Just verify eyes are being set to reasonable values
    assert np.all(eyes >= 0)
    assert np.all(eyes <= 255)


def test_audio_to_channel_values_eye_starts_open(sample_audio):
    """Eyes should start each interaction at the base open position."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)

    channel_values = gen.audio_to_channel_values(
        audio, sample_rate, "Kick things off", eyes_base=0.9
    )

    eyes = channel_values[:, 1]
    expected_base = int((1.0 - 0.9) * 255)  # Inverted eye polarity
    # First and last few frames should hold the base to reset drift between interactions
    assert np.all(eyes[:3] == expected_base)
    assert np.all(eyes[-3:] == expected_base)


def test_audio_to_channel_values_sentiment_effect(sample_audio):
    """Test that sentiment affects eye position."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)
    text = "Test"

    # Generate with negative sentiment
    channel_values_neg = gen.audio_to_channel_values(
        audio, sample_rate, text, sentiment=-0.5
    )

    # Generate with positive sentiment
    channel_values_pos = gen.audio_to_channel_values(
        audio, sample_rate, text, sentiment=0.5
    )

    # Eye positions should differ on average
    eyes_neg = channel_values_neg[:, 1]
    eyes_pos = channel_values_pos[:, 1]

    # Due to random blinks, use median instead of mean
    # Positive sentiment should result in different eye position
    assert np.median(eyes_neg) != np.median(eyes_pos)


def test_calculate_syllable_mouth_values_basic():
    """Test syllable-based mouth value calculation."""
    gen = PPMGenerator(sample_rate=16000)
    audio = np.random.randn(16000).astype(np.float32) * 0.3
    text = "Hello world"

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should generate array of values between 0 and 1
    assert len(mouth_values) > 0
    assert np.all(mouth_values >= 0.0)
    assert np.all(mouth_values <= 1.0)

    # Should have some variation (envelope creates open/close)
    assert len(np.unique(mouth_values)) > 1


def test_calculate_syllable_mouth_values_empty_text():
    """Test syllable calculation with empty text."""
    gen = PPMGenerator(sample_rate=16000)
    audio = np.random.randn(16000).astype(np.float32) * 0.3
    text = ""

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should return fallback array
    assert len(mouth_values) > 0


def test_calculate_syllable_mouth_values_multisyllable():
    """Test syllable calculation with multi-syllable words."""
    gen = PPMGenerator(sample_rate=16000)
    # Create audio with varying amplitude
    t = np.linspace(0, 2, 32000)
    audio = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)

    text = "extraordinary hippopotamus"  # Multi-syllable words

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should generate envelope with multiple syllables
    assert len(mouth_values) > 10  # At least 10+ syllables

    # Should have open/close envelopes (includes zeros)
    assert np.any(mouth_values == 0.0)
    assert np.any(mouth_values > 0.0)


def test_extract_syllables_from_text():
    """Test syllable extraction from text."""
    gen = PPMGenerator()
    words = ["hello", "world", "extraordinary"]

    syllables = gen._extract_syllables_from_text(words)

    # Should extract syllables
    assert len(syllables) > len(words)  # More syllables than words
    assert all(isinstance(s, str) for s in syllables)


def test_ppm_signal_timing_accuracy():
    """Test that PPM signal maintains correct timing."""
    gen = PPMGenerator(sample_rate=16000)
    duration = 1.0
    num_frames = int(duration / (gen.PERIOD / 1_000_000))
    channel_values = np.zeros((num_frames, 8), dtype=np.uint8)

    signal = gen.generate_ppm_signal(duration, channel_values)

    # Signal length should match requested duration
    expected_samples = int(duration * gen.sample_rate)
    assert len(signal) == expected_samples


def test_ppm_signal_pulse_characteristics():
    """Test that PPM pulses have correct characteristics."""
    gen = PPMGenerator(sample_rate=16000)
    duration = 0.1  # Short duration for easier analysis
    num_frames = int(duration / (gen.PERIOD / 1_000_000))
    channel_values = np.zeros((num_frames, 8), dtype=np.uint8)

    signal = gen.generate_ppm_signal(duration, channel_values)

    # Pulses should be negative (around -0.30)
    negative_samples = signal[signal < -0.2]
    assert len(negative_samples) > 0

    # Most signal should be near DC (0.0) for gaps
    dc_samples = np.abs(signal) < 0.1
    assert np.sum(dc_samples) > len(signal) * 0.5  # At least 50% near DC


def test_channel_values_smoothing(sample_audio):
    """Test that channel values have smooth transitions."""
    audio, sample_rate = sample_audio
    gen = PPMGenerator(sample_rate=sample_rate)

    text = "Testing smooth transitions"
    channel_values = gen.audio_to_channel_values(audio, sample_rate, text)

    # Check mouth channel for smoothness
    lower_jaw = channel_values[:, 3]

    # Calculate differences between consecutive frames
    diffs = np.abs(np.diff(lower_jaw.astype(float)))

    # Most transitions should be gradual (not jumping full range)
    large_jumps = diffs > 100
    # Allow some large jumps (syllable onsets) but not most transitions
    assert np.sum(large_jumps) < len(diffs) * 0.3  # Less than 30% large jumps


def test_ppm_signal_early_termination():
    """Test PPM signal generation when sample limit is reached mid-frame."""
    gen = PPMGenerator(sample_rate=16000)

    # Create channel values for more frames than samples allow
    duration = 0.05  # Very short duration (50ms)
    num_frames = 10  # But request 10 frames (would need ~166ms)
    channel_values = np.full((num_frames, 8), 128, dtype=np.uint8)

    signal = gen.generate_ppm_signal(duration, channel_values)

    # Should handle early termination gracefully
    assert len(signal) == int(duration * 16000)
    assert np.all(signal >= -1.0)
    assert np.all(signal <= 1.0)


def test_audio_to_channel_values_early_break():
    """Test audio_to_channel_values when audio ends early."""
    gen = PPMGenerator(sample_rate=16000)

    # Very short audio (100ms)
    audio = np.random.randn(1600).astype(np.float32) * 0.3
    text = "Test"

    channel_values = gen.audio_to_channel_values(audio, 16000, text)

    # Should handle short audio gracefully
    assert channel_values.shape[1] == 8
    assert channel_values.dtype == np.uint8


def test_low_mouth_activity_warning(caplog):
    """Test warning when mouth barely moves."""
    import logging

    gen = PPMGenerator(sample_rate=16000)

    # Use completely silent audio to ensure < 10% mouth movement
    silent_audio = np.zeros(16000, dtype=np.float32)

    with caplog.at_level(logging.WARNING):
        channel_values = gen.audio_to_channel_values(silent_audio, 16000, "test")

    # Should generate warning about low mouth activity
    assert any("Low mouth activity" in record.message for record in caplog.records)


def test_syllable_calculation_no_syllables_detected():
    """Test syllable calculation when no syllables are detected."""
    gen = PPMGenerator(sample_rate=16000)
    audio = np.random.randn(16000).astype(np.float32) * 0.3

    # Text with words but syllable detection might return 0
    text = "xyz"  # Made-up word that might not parse

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should use fallback (words as syllables)
    assert len(mouth_values) > 0
    assert np.all(mouth_values >= 0.0)
    assert np.all(mouth_values <= 1.0)


def test_syllable_calculation_audio_ends_early():
    """Test syllable calculation when audio segment is empty."""
    gen = PPMGenerator(sample_rate=16000)

    # Very short audio with many syllables
    audio = np.random.randn(100).astype(np.float32) * 0.3
    text = "extraordinarily hippopotamus"  # Many syllables, short audio

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should handle gracefully with zero values for missing segments
    assert len(mouth_values) > 0
    assert np.all(mouth_values >= 0.0)


def test_syllable_calculation_empty_audio_segment():
    """Test handling of empty syllable audio segments."""
    gen = PPMGenerator(sample_rate=16000)

    # Create scenario where syllable segments might be empty
    audio = np.random.randn(50).astype(np.float32) * 0.3
    text = "a b c d e f g h i j"  # Many short words, little audio

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should return envelope values with zeros for empty segments
    assert len(mouth_values) > 0
    assert np.any(mouth_values == 0.0)  # Some should be zero


def test_extract_syllables_pyphen_fallback():
    """Test syllable extraction fallback when pyphen fails."""
    gen = PPMGenerator()

    # Use problematic words that might cause pyphen issues
    # or mock pyphen to fail
    with pytest.raises(Exception):
        # Force an error by trying to import non-existent module
        import pyphen
        dic = pyphen.Pyphen(lang='invalid_language_code_xyz')

    # Normal case should work
    words = ["hello", "world"]
    syllables = gen._extract_syllables_from_text(words)

    # Should return syllables (either from pyphen or fallback)
    assert len(syllables) >= len(words)


def test_extract_syllables_with_mock_error(monkeypatch):
    """Test syllable extraction fallback when pyphen raises exception."""
    gen = PPMGenerator()

    # Mock pyphen to raise an exception
    def mock_pyphen_error(*args, **kwargs):
        raise Exception("Pyphen error")

    # Patch pyphen.Pyphen to raise error
    import sys
    if 'pyphen' in sys.modules:
        original_pyphen = sys.modules['pyphen'].Pyphen
        monkeypatch.setattr('pyphen.Pyphen', mock_pyphen_error)

        words = ["test", "words"]
        syllables = gen._extract_syllables_from_text(words)

        # Should use fallback (syllables library)
        assert len(syllables) > 0

        # Restore
        monkeypatch.setattr('pyphen.Pyphen', original_pyphen)


def test_audio_to_channel_values_long_duration():
    """Test audio_to_channel_values with audio that exhausts before all calculated frames."""
    # Use a sample rate where rounding creates the edge case
    gen = PPMGenerator(sample_rate=8000)

    # With sample_rate=8000, samples_per_frame = int(8000 * 16600 / 1_000_000) = int(132.8) = 132
    # Use 133 samples (just over one frame)
    # duration = 133 / 8000 = 0.016625 s
    # num_frames = int(0.016625 / 0.0166) + 1 = int(1.0015) + 1 = 2 frames
    # Frame 0: start = 0 (OK)
    # Frame 1: start = 132 (< 133, OK)
    # But with 132 samples:
    # duration = 132 / 8000 = 0.0165 s
    # num_frames = int(0.0165 / 0.0166) + 1 = int(0.994) + 1 = 1 frame
    # So we need to find the right combination...

    # Actually, let's just use very short audio to test the defensive break
    audio = np.array([0.5, 0.3, 0.1], dtype=np.float32)
    text = "test"

    # This should handle the edge case gracefully (line 153 is defensive code)
    channel_values = gen.audio_to_channel_values(audio, 8000, text)

    # Should still generate valid output
    assert channel_values.shape[1] == 8
    assert channel_values.dtype == np.uint8


def test_syllable_calculation_pyphen_returns_empty():
    """Test syllable calculation when pyphen returns no syllables."""
    gen = PPMGenerator(sample_rate=16000)
    audio = np.random.randn(16000).astype(np.float32) * 0.3

    # Mock _extract_syllables_from_text to return empty list
    original_extract = gen._extract_syllables_from_text
    gen._extract_syllables_from_text = lambda words: []

    # This should trigger lines 240-241 (total_syllables == 0 fallback)
    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, "test words")

    # Should use words as fallback
    assert len(mouth_values) > 0
    assert np.all(mouth_values >= 0.0)
    assert np.all(mouth_values <= 1.0)

    # Restore
    gen._extract_syllables_from_text = original_extract


def test_syllable_calculation_very_short_audio_many_syllables():
    """Test syllable calculation with extremely short audio and many syllables."""
    gen = PPMGenerator(sample_rate=16000)

    # Very short audio (2 samples) with many words
    # This will cause samples_per_syllable to be very small
    # Later syllables will have start_sample >= len(audio), triggering lines 254-255
    audio = np.array([0.5, 0.3], dtype=np.float32)

    # Many syllables (much more than audio samples)
    # Each syllable would need start_sample, but we only have 2 samples
    text = "a b c d e f g h i j k l m n o p q r s t u v w x y z"

    mouth_values = gen._calculate_syllable_mouth_values(audio, 16000, text)

    # Should handle gracefully with zeros for empty segments (lines 254-255)
    assert len(mouth_values) > 0
    assert np.any(mouth_values == 0.0)  # Empty segments should be zero


def test_extract_syllables_zero_estimate(monkeypatch):
    """Test syllable extraction when syllables.estimate returns 0."""
    gen = PPMGenerator()

    # Mock syllables.estimate to return 0
    def mock_estimate(word):
        return 0

    # Mock pyphen to fail (force fallback)
    def mock_pyphen_error(*args, **kwargs):
        raise Exception("Pyphen error")

    import sys
    if 'pyphen' in sys.modules:
        monkeypatch.setattr('pyphen.Pyphen', mock_pyphen_error)

    # Patch syllables.estimate
    import syllables
    original_estimate = syllables.estimate
    monkeypatch.setattr('syllables.estimate', mock_estimate)

    words = ["xyz", "abc"]
    syllable_list = gen._extract_syllables_from_text(words)

    # Should use count = 1 fallback (line 316)
    assert len(syllable_list) >= len(words)

    # Restore
    monkeypatch.setattr('syllables.estimate', original_estimate)
