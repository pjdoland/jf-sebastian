"""
Animatronic control signal generation for 1985 Teddy Ruxpin.
Generates PPM control signals with syllable-based lip sync.
"""

import logging
import io
import subprocess
import tempfile
import os
from typing import Optional, Tuple

import numpy as np
from scipy import signal as scipy_signal
from scipy.io import wavfile
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from teddy_ruxpin.config import settings
from teddy_ruxpin.modules.ppm_generator import PPMGenerator

logger = logging.getLogger(__name__)


class AnimatronicControlGenerator:
    """
    Generates PPM control signals for Teddy Ruxpin's motors.
    Creates stereo output: LEFT = voice audio, RIGHT = PPM control signals.
    Uses syllable-based lip sync for accurate mouth movements.
    """

    def __init__(self):
        """Initialize control generator."""
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        # Generate PPM at 44.1kHz to avoid resampling artifacts
        self.ppm_sample_rate = 44100
        self.ppm_generator = PPMGenerator(sample_rate=self.ppm_sample_rate)
        logger.info(f"Animatronic control generator initialized (PPM mode, {self.ppm_sample_rate}Hz)")

    def create_stereo_output(
        self,
        voice_audio_mp3: bytes,
        response_text: str
    ) -> Optional[Tuple[np.ndarray, int]]:
        """
        Create stereo audio output with voice and PPM control signals.

        Args:
            voice_audio_mp3: Voice audio data from TTS (MP3 format)
            response_text: Original text for sentiment analysis and lip sync

        Returns:
            Tuple of (stereo_audio_array, sample_rate), or None on error
            stereo_audio_array shape: (num_samples, 2) where:
                - Column 0: LEFT channel (voice)
                - Column 1: RIGHT channel (PPM control signals)
        """
        try:
            # Convert MP3 to PCM audio array
            voice_audio = self._mp3_to_pcm(voice_audio_mp3)

            if voice_audio is None:
                logger.error("Failed to convert MP3 to PCM")
                return None

            # Analyze sentiment for eye control
            sentiment = self._analyze_sentiment(response_text)

            # Resample voice audio to match PPM sample rate
            # (Resample voice, NOT PPM, to preserve precise pulse timing)
            voice_duration = len(voice_audio) / settings.SAMPLE_RATE
            voice_samples_needed = int(voice_duration * self.ppm_sample_rate)
            voice_audio_resampled = scipy_signal.resample(voice_audio, voice_samples_needed)

            # Generate PPM channel values using syllable-based lip sync
            channel_values = self.ppm_generator.audio_to_channel_values(
                voice_audio,
                settings.SAMPLE_RATE,
                text=response_text,
                eyes_base=0.5,
                sentiment=sentiment
            )

            # Generate PPM control signal at 44.1kHz (no resampling needed)
            ppm_signal = self.ppm_generator.generate_ppm_signal(voice_duration, channel_values)

            # Ensure same length
            min_length = min(len(voice_audio_resampled), len(ppm_signal))
            voice_audio_resampled = voice_audio_resampled[:min_length]
            ppm_signal = ppm_signal[:min_length]

            # Apply channel-specific gains to balance audio vs control
            # Voice: boost by 25% for louder audio
            voice_gain = 0.7 * 1.25  # 87.5%
            voice_audio_resampled = voice_audio_resampled * voice_gain

            # Control: reduce by 25% to minimize bleedover
            control_gain = 0.7 * 0.75  # 52.5%
            ppm_signal = ppm_signal * control_gain

            # Create stereo array
            # LEFT=voice, RIGHT=control (original Teddy Ruxpin format)
            stereo_audio = np.column_stack((voice_audio_resampled, ppm_signal))

            logger.info(
                f"Stereo output created (PPM): {stereo_audio.shape[0]} samples at {self.ppm_sample_rate}Hz, "
                f"sentiment={sentiment:.2f}, {len(channel_values)} PPM frames, "
                f"voice_gain={voice_gain:.2f}, control_gain={control_gain:.2f}"
            )

            return stereo_audio, self.ppm_sample_rate

        except Exception as e:
            logger.error(f"Error creating stereo output: {e}", exc_info=True)
            return None

    def _mp3_to_pcm(self, mp3_data: bytes) -> Optional[np.ndarray]:
        """
        Convert MP3 audio to PCM array using FFmpeg.

        Args:
            mp3_data: MP3 audio bytes

        Returns:
            Numpy array of audio samples (normalized to -1.0 to 1.0)
        """
        try:
            # Write MP3 to temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as mp3_file:
                mp3_file.write(mp3_data)
                mp3_path = mp3_file.name

            # Use FFmpeg to convert MP3 to raw PCM
            # Output: mono, 16-bit signed, little-endian, at target sample rate
            result = subprocess.run([
                'ffmpeg',
                '-i', mp3_path,
                '-f', 's16le',  # 16-bit signed little-endian PCM
                '-acodec', 'pcm_s16le',
                '-ac', '1',  # mono
                '-ar', str(settings.SAMPLE_RATE),  # target sample rate
                '-'  # output to stdout
            ], capture_output=True, check=True)

            # Clean up temp file
            os.unlink(mp3_path)

            # Convert to numpy array
            samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)

            # Normalize to -1.0 to 1.0
            samples = samples / 32768.0  # 16-bit audio max value

            return samples

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error converting MP3 to PCM: {e}", exc_info=True)
            return None

    def _analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Sentiment score (-1.0 to 1.0, where positive = happy, negative = sad)
        """
        try:
            scores = self.sentiment_analyzer.polarity_scores(text)
            compound_score = scores['compound']
            logger.debug(f"Sentiment analysis: {text[:50]}... = {compound_score:.2f}")
            return compound_score
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return 0.0  # Neutral


def save_stereo_wav(stereo_audio: np.ndarray, sample_rate: int, filename: str):
    """
    Save stereo audio to WAV file for debugging.

    Args:
        stereo_audio: Stereo audio array (num_samples, 2)
        sample_rate: Sample rate in Hz
        filename: Output filename
    """
    try:
        # Convert to int16 for WAV
        audio_int16 = (stereo_audio * 32767).astype(np.int16)

        wavfile.write(filename, sample_rate, audio_int16)
        logger.info(f"Stereo audio saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving stereo audio: {e}", exc_info=True)
