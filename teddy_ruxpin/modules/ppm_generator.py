"""
PPM (Pulse Position Modulation) generator for Teddy Ruxpin control track.
Based on the original Teddy Ruxpin tape format.
"""

import logging
import numpy as np
from teddy_ruxpin.config import settings

logger = logging.getLogger(__name__)


class PPMGenerator:
    """
    Generates PPM control signals for Teddy Ruxpin.

    PPM Format:
    - Frame period: 20ms (50 Hz)
    - 8 channels per frame
    - Each channel: HIGH pulse (250µs) + LOW gap (850-1750µs)
    - Gap duration encodes motor position (0-255 maps to min-max gap)
    """

    def __init__(self, sample_rate: int = 16000):
        """
        Initialize PPM generator.

        Args:
            sample_rate: Audio sample rate in Hz
        """
        self.sample_rate = sample_rate

        # PPM timing parameters (in microseconds) - Svengali timing
        self.PERIOD = 16600  # 16.6ms frame period (~60 Hz)
        self.PAUSE_DURATION = 400  # High pulse duration
        self.MIN_GAP = 630  # Minimum gap duration
        self.MAX_GAP = 1590  # Maximum gap duration

        # Channel configuration
        self.NUM_CHANNELS = 8

        # Convert timings to samples
        self.period_samples = int(self.PERIOD / 1_000_000 * sample_rate)
        self.pause_samples = int(self.PAUSE_DURATION / 1_000_000 * sample_rate)

        logger.info(f"PPM Generator initialized: {sample_rate}Hz, period={self.period_samples} samples")

    def generate_ppm_signal(self, duration_seconds: float, channel_values: np.ndarray) -> np.ndarray:
        """
        Generate PPM control signal for given duration.

        Args:
            duration_seconds: Duration of signal to generate
            channel_values: Array of shape (num_frames, 8) with values 0-255 for each channel
                           Each frame corresponds to one 20ms period

        Returns:
            PPM signal as numpy array (normalized -1 to 1)
        """
        total_samples = int(duration_seconds * self.sample_rate)
        signal = np.zeros(total_samples, dtype=np.float32)

        num_frames = len(channel_values)
        sample_idx = 0

        for frame_idx in range(num_frames):
            if sample_idx >= total_samples:
                break

            frame_start = sample_idx

            # Generate 8 channels for this frame
            for ch in range(self.NUM_CHANNELS):
                if sample_idx >= total_samples:
                    break

                # Get channel value (0-255)
                value = channel_values[frame_idx, ch]

                # Calculate gap duration based on value
                gap_duration_us = self.MIN_GAP + (value / 255.0) * (self.MAX_GAP - self.MIN_GAP)
                gap_samples = int(gap_duration_us / 1_000_000 * self.sample_rate)

                # HIGH pulse - negative going, centered at DC=0 (matches original tapes)
                pulse_end = min(sample_idx + self.pause_samples, total_samples)
                signal[sample_idx:pulse_end] = -0.30  # HIGH pulse (negative, 30% amplitude like original)
                sample_idx = pulse_end

                # Gap at DC center (0.0 = silence)
                gap_end = min(sample_idx + gap_samples, total_samples)
                signal[sample_idx:gap_end] = 0.0  # Gap (DC center)
                sample_idx = gap_end

            # Fill rest of frame period with DC offset (sync gap)
            frame_end = min(frame_start + self.period_samples, total_samples)
            if sample_idx < frame_end:
                signal[sample_idx:frame_end] = 0.0  # Sync gap at DC

            sample_idx = frame_end

        # Apply light low-pass filter to round pulse edges slightly
        # Original tapes have ~0.6ms rise time, but too much filtering creates glitchy motor behavior
        from scipy import signal as scipy_signal

        # Use a higher cutoff (5kHz) to preserve pulse definition while softening edges
        nyquist = self.sample_rate / 2
        cutoff = 5000  # Hz - higher cutoff preserves pulse shape better
        b, a = scipy_signal.butter(2, cutoff / nyquist, btype='low')  # 2nd order (gentler)
        signal_filtered = scipy_signal.filtfilt(b, a, signal)

        return signal_filtered

    def audio_to_channel_values(
        self,
        audio: np.ndarray,
        sample_rate: int,
        text: str = "",
        eyes_base: float = 0.9,
        sentiment: float = 0.0
    ) -> np.ndarray:
        """
        Convert audio amplitude to PPM channel values using syllable-based timing.

        Args:
            audio: Audio waveform (mono, normalized -1 to 1)
            sample_rate: Audio sample rate
            text: Text being spoken (for syllable detection)
            eyes_base: Base eye position (0-1, default 0.9 to start interactions open)
            sentiment: Sentiment score (-1 to 1) for eye modulation

        Returns:
            Channel values array of shape (num_frames, 8)
        """
        # Calculate number of frames needed (one frame per 16.6ms)
        duration = len(audio) / sample_rate
        num_frames = int(duration / (self.PERIOD / 1_000_000)) + 1

        # Initialize channel values (all zeros)
        channel_values = np.zeros((num_frames, self.NUM_CHANNELS), dtype=np.uint8)
        frames_generated = 0
        blink_count = 0

        # Blink state tracking
        blink_state = None  # None, 'closing', 'closed', 'opening'
        blink_frame_counter = 0
        blink_start_position = 0.0  # Store eye position when blink starts
        blink_target_position = 0.0  # Store where eyes should return to
        BLINK_CLOSE_FRAMES = 5   # Frames to close eyes (~83ms at 60Hz)
        BLINK_HOLD_FRAMES = 2    # Frames to hold closed (~33ms)
        BLINK_OPEN_FRAMES = 5    # Frames to reopen (~83ms)

        # Parse syllables from text for better lip sync timing
        syllable_values = self._calculate_syllable_mouth_values(audio, sample_rate, text)

        # Clamp inputs for eyes and sentiment
        base_eye_position = np.clip(eyes_base, 0, 1)
        sentiment = float(np.clip(sentiment, -1.0, 1.0))
        # Hold the eyes at the base position at the start and end of each clip so
        # every interaction begins and returns to a known open state.
        settle_frames_start = 3
        settle_frames_end = 3
        settle_end_start_idx = max(num_frames - settle_frames_end, 0)

        # Samples per PPM frame
        samples_per_frame = int(sample_rate * self.PERIOD / 1_000_000)

        # Generate mouth movements based on syllable timing
        for frame_idx in range(num_frames):
            start_sample = frame_idx * samples_per_frame
            end_sample = min(start_sample + samples_per_frame, len(audio))

            if start_sample >= len(audio):
                break
            frames_generated += 1

            # Get syllable-based mouth value for this frame's timestamp
            time_in_audio = start_sample / sample_rate
            syllable_idx = int(time_in_audio / duration * len(syllable_values))
            syllable_idx = min(syllable_idx, len(syllable_values) - 1)

            mouth_value = syllable_values[syllable_idx]

            # Apply smooth interpolation between syllables
            if frame_idx > 0:
                prev_mouth = channel_values[frame_idx - 1, 3] / 255.0
                # Fast attack on syllable start, slower release
                if mouth_value > prev_mouth:
                    attack = 0.15  # Fast attack for syllable onset
                    mouth_value = attack * prev_mouth + (1 - attack) * mouth_value
                else:
                    release = 0.35  # Moderate release between syllables
                    mouth_value = release * prev_mouth + (1 - release) * mouth_value

            channel_values[frame_idx, 3] = int(mouth_value * 255)  # Ch3: Lower jaw/mouth
            channel_values[frame_idx, 2] = int(mouth_value * 0.7 * 255)  # Ch2: Upper jaw (70% of lower)

            # Eye control based on sentiment (much more subtle)
            if frame_idx < settle_frames_start or frame_idx >= settle_end_start_idx:
                # Force initial and final frames to the base position to reset between interactions
                eye_position = base_eye_position
            else:
                # Map sentiment from -1..1 to eye position 0..1 around the base
                # Reduced from ±30% to ±8% for much subtler movement
                eye_position = base_eye_position + sentiment * 0.08
                eye_position = np.clip(eye_position, 0, 1)

            # Multi-frame blink animation
            # Check if we should start a new blink (only if not already blinking)
            if (
                blink_state is None
                and settle_frames_start <= frame_idx < settle_end_start_idx
                and np.random.random() < 0.008  # ~0.8% chance per frame (~once per 2 seconds at 60Hz)
            ):
                blink_state = 'closing'
                blink_frame_counter = 0
                blink_start_position = eye_position  # Save current position
                blink_count += 1

            # Handle blink state machine
            if blink_state == 'closing':
                # Animate eyes closing from start position to fully closed
                progress = blink_frame_counter / BLINK_CLOSE_FRAMES
                eye_position = blink_start_position * (1.0 - progress)  # Gradually close to 0
                blink_frame_counter += 1
                if blink_frame_counter >= BLINK_CLOSE_FRAMES:
                    blink_state = 'closed'
                    blink_frame_counter = 0

            elif blink_state == 'closed':
                # Hold eyes fully closed
                eye_position = 0.0  # Fully closed
                blink_frame_counter += 1
                if blink_frame_counter >= BLINK_HOLD_FRAMES:
                    blink_state = 'opening'
                    blink_frame_counter = 0
                    # Calculate where eyes should return to
                    blink_target_position = base_eye_position + sentiment * 0.08
                    blink_target_position = np.clip(blink_target_position, 0, 1)

            elif blink_state == 'opening':
                # Animate eyes opening from closed to target position
                progress = blink_frame_counter / BLINK_OPEN_FRAMES
                eye_position = blink_target_position * progress  # Gradually open to target
                blink_frame_counter += 1
                if blink_frame_counter >= BLINK_OPEN_FRAMES:
                    blink_state = None  # Blink complete
                    blink_frame_counter = 0

            # Keep a floor on eye openness when not blinking (relaxed from 75% to allow more range)
            if blink_state is None:
                min_eye_open = max(base_eye_position * 0.85, 0.75)  # Keep eyes mostly open
                eye_position = max(eye_position, min_eye_open)

            # Hardware expects inverted polarity: higher command closes lids, so flip to keep
            # higher logical openness mapping to lower command value.
            eye_command = 1.0 - eye_position
            channel_values[frame_idx, 1] = int(eye_command * 255)  # Ch1: Eyes (inverted)

        # Trim to the frames we actually generated (avoids trailing zeros from the prealloc)
        if frames_generated > 0:
            channel_values = channel_values[:frames_generated]
        else:
            channel_values = channel_values[:1]

        # Enforce base eye position on the true first/last frames (after trimming)
        # Invert since hardware expects inverted polarity (higher = more closed)
        base_value = int((1.0 - base_eye_position) * 255)
        start_frames = min(settle_frames_start, len(channel_values))
        end_frames_start = max(len(channel_values) - settle_frames_end, 0)
        if start_frames > 0:
            channel_values[:start_frames, 1] = base_value
        if settle_frames_end > 0:
            channel_values[end_frames_start:, 1] = base_value

        # Validate and log mouth movement statistics
        mouth_values = channel_values[:, 3]  # Lower jaw
        non_zero_frames = np.sum(mouth_values > 0)
        avg_mouth = np.mean(mouth_values[mouth_values > 0]) if non_zero_frames > 0 else 0
        max_mouth = np.max(mouth_values)

        logger.info(
            f"Generated {num_frames} PPM frames from {duration:.2f}s audio - "
            f"Mouth: {non_zero_frames}/{num_frames} active frames ({non_zero_frames/num_frames*100:.1f}%), "
            f"avg={avg_mouth:.1f}, max={max_mouth}"
        )

        # Sanity check: warn if mouth barely moves
        if non_zero_frames < num_frames * 0.1:
            logger.warning(f"Low mouth activity detected! Only {non_zero_frames}/{num_frames} frames have movement")

        # Log eye movement statistics for debugging excessive closing
        eyes_values = channel_values[:, 1]  # Already inverted command values
        if len(eyes_values) > 0:
            eye_stats = {
                "min": np.min(eyes_values) / 255.0,
                "median": float(np.median(eyes_values) / 255.0),
                "max": np.max(eyes_values) / 255.0,
                "blinks": blink_count,
                "frames": len(eyes_values),
                "base": base_eye_position,
                "sentiment": sentiment,
            }
            logger.info(
                "Eye stats: base={base:.2f}, sentiment={sentiment:+.2f}, "
                "median={median:.3f}, min={min:.3f}, max={max:.3f}, "
                "blinks={blinks} over {frames} frames".format(**eye_stats)
            )

        return channel_values

    def _calculate_syllable_mouth_values(
        self,
        audio: np.ndarray,
        sample_rate: int,
        text: str
    ) -> np.ndarray:
        """
        Calculate mouth opening values per syllable with simple open-close envelope.

        Each syllable creates an envelope: closed → open (amplitude-based) → closed
        This creates a natural "chewing" motion.

        Args:
            audio: Audio waveform
            sample_rate: Audio sample rate
            text: Text being spoken

        Returns:
            Array of mouth values (0-1) creating envelopes for each syllable
        """
        import syllables
        import re

        # Clean text and extract syllables
        words = re.findall(r'\b\w+\b', text.lower())

        if not words:
            # No text, fall back to simple amplitude
            return np.array([0.5])

        # Extract syllables
        syllable_list = self._extract_syllables_from_text(words)
        total_syllables = len(syllable_list)

        if total_syllables == 0:
            total_syllables = len(words)
            syllable_list = words

        # Divide audio into syllable segments
        samples_per_syllable = len(audio) // total_syllables if total_syllables > 0 else len(audio)

        # Create envelope values: 3 points per syllable (start, peak, end)
        envelope_values = []

        for syl_idx in range(total_syllables):
            start_sample = syl_idx * samples_per_syllable
            end_sample = min(start_sample + samples_per_syllable, len(audio))

            if start_sample >= len(audio):
                envelope_values.extend([0.0, 0.0, 0.0])
                continue

            # Get audio for this syllable
            syllable_audio = audio[start_sample:end_sample]

            if len(syllable_audio) == 0:
                envelope_values.extend([0.0, 0.0, 0.0])
                continue

            # Calculate amplitude for this syllable (peak + RMS blend)
            peak = np.max(np.abs(syllable_audio))
            rms = np.sqrt(np.mean(syllable_audio ** 2))
            amplitude = 0.7 * peak + 0.3 * rms

            # Apply gain for mouth movement (scaled for visibility)
            mouth_opening = np.clip(amplitude * 12.0, 0, 1)

            # Create envelope: closed → open → closed
            envelope_values.extend([
                0.0,              # Start: closed
                mouth_opening,    # Middle: open (amplitude-based)
                0.0               # End: closed
            ])

        logger.debug(
            f"Generated {len(envelope_values)} envelope values from {total_syllables} syllables"
        )

        return np.array(envelope_values)

    def _extract_syllables_from_text(self, words: list) -> list:
        """
        Extract syllables from words using pyphen.

        Args:
            words: List of words

        Returns:
            List of syllable strings
        """
        try:
            import pyphen
            dic = pyphen.Pyphen(lang='en_US')

            syllable_list = []
            for word in words:
                # Split word into syllables using pyphen
                syllabified = dic.inserted(word, hyphen='|')
                word_syllables = syllabified.split('|')
                syllable_list.extend(word_syllables)

            return syllable_list

        except Exception as e:
            logger.warning(f"Error extracting syllables with pyphen: {e}, using fallback")
            # Fallback: estimate syllables per word
            import syllables
            syllable_list = []
            for word in words:
                count = syllables.estimate(word)
                if count == 0:
                    count = 1
                # Split word evenly (rough approximation)
                syllable_list.extend([word] * count)
            return syllable_list
