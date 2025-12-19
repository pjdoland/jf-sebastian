"""
Stereo audio output pipeline for Teddy Ruxpin.
Plays voice audio (left channel) and control signals (right channel) through selected device.
"""

import logging
import threading
import time
from typing import Optional, Callable

import numpy as np
import pyaudio

from jf_sebastian.config import settings
from jf_sebastian.utils import find_audio_device_by_name

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Plays stereo audio through selected output device.
    Supports blocking and non-blocking playback modes.
    """

    def __init__(self, on_playback_complete: Optional[Callable[[], None]] = None):
        """
        Initialize audio player.

        Args:
            on_playback_complete: Optional callback when playback finishes
        """
        self.on_playback_complete = on_playback_complete
        self._playing = False
        self._thread: Optional[threading.Thread] = None
        # Initialize PyAudio once and reuse it to avoid CoreAudio issues on macOS
        self._pyaudio = pyaudio.PyAudio()
        logger.info("Audio player initialized")

    def play_stereo(
        self,
        stereo_audio: np.ndarray,
        sample_rate: int,
        blocking: bool = True,
        preroll_ms: Optional[int] = None
    ) -> bool:
        """
        Play stereo audio.

        Args:
            stereo_audio: Stereo audio array (num_samples, 2)
            sample_rate: Sample rate in Hz
            blocking: If True, wait for playback to complete. If False, play in background.
            preroll_ms: Optional preroll of silence in milliseconds to avoid clipped starts.
                Defaults to settings.PLAYBACK_PREROLL_MS when None.

        Returns:
            True if playback started successfully
        """
        if self._playing:
            logger.warning("Already playing audio")
            return False

        try:
            # Add a short preroll of silence so devices have time to spin up before audio begins
            if preroll_ms is None:
                preroll_ms = settings.PLAYBACK_PREROLL_MS
            if preroll_ms and preroll_ms > 0:
                preroll_samples = int(sample_rate * (preroll_ms / 1000.0))
                if preroll_samples > 0:
                    silence = np.zeros((preroll_samples, 2), dtype=stereo_audio.dtype)
                    stereo_audio = np.vstack((silence, stereo_audio))

            logger.info(f"Starting audio playback ({stereo_audio.shape[0]} samples at {sample_rate}Hz)")

            if blocking:
                self._play_blocking(stereo_audio, sample_rate)
            else:
                self._thread = threading.Thread(
                    target=self._play_blocking,
                    args=(stereo_audio, sample_rate),
                    daemon=True
                )
                self._thread.start()

            return True

        except Exception as e:
            logger.error(f"Error starting audio playback: {e}", exc_info=True)
            return False

    def _play_blocking(self, stereo_audio: np.ndarray, sample_rate: int):
        """Play audio in blocking mode."""
        self._playing = True
        stream = None

        try:
            # Get output device by name (None = system default)
            device_index = None

            if settings.OUTPUT_DEVICE_NAME:
                # Find device by name
                device_index = find_audio_device_by_name(
                    self._pyaudio,
                    settings.OUTPUT_DEVICE_NAME,
                    "output"
                )
                if device_index is None:
                    logger.warning(f"Could not find output device '{settings.OUTPUT_DEVICE_NAME}', using default")

            # Get device info
            if device_index is not None and device_index >= 0:
                device_info = self._pyaudio.get_device_info_by_index(device_index)
                device_sample_rate = int(device_info['defaultSampleRate'])
            else:
                # Use default device
                default_device = self._pyaudio.get_default_output_device_info()
                device_sample_rate = int(default_device['defaultSampleRate'])
                device_index = None

            logger.info(f"Output device sample rate: {device_sample_rate}Hz, input audio: {sample_rate}Hz")

            # Resample if needed
            if sample_rate != device_sample_rate:
                logger.info(f"Resampling audio from {sample_rate}Hz to {device_sample_rate}Hz")
                from scipy import signal as scipy_signal

                # Calculate new length
                num_samples = int(len(stereo_audio) * device_sample_rate / sample_rate)

                # Resample each channel
                left_resampled = scipy_signal.resample(stereo_audio[:, 0], num_samples)
                right_resampled = scipy_signal.resample(stereo_audio[:, 1], num_samples)

                # Combine back to stereo
                stereo_audio = np.column_stack((left_resampled, right_resampled))
                sample_rate = device_sample_rate

            # Convert to int16
            audio_int16 = (stereo_audio * 32767).astype(np.int16)

            # Open output stream with retry logic for macOS CoreAudio issues
            max_retries = 3
            retry_delay = 0.1

            for attempt in range(max_retries):
                try:
                    stream = self._pyaudio.open(
                        format=pyaudio.paInt16,
                        channels=2,  # Stereo
                        rate=sample_rate,
                        output=True,
                        output_device_index=device_index,
                        frames_per_buffer=1024,
                    )
                    break  # Success, exit retry loop
                except OSError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Audio stream open failed (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise  # Final attempt failed, raise the error

            # Play audio
            stream.write(audio_int16.tobytes())

            # Wait for playback to complete
            stream.stop_stream()
            stream.close()
            stream = None

            logger.info("Audio playback completed")

        except Exception as e:
            logger.error(f"Error during audio playback: {e}", exc_info=True)

        finally:
            # Clean up stream if it's still open
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass

            self._playing = False

            # Call completion callback
            if self.on_playback_complete:
                try:
                    self.on_playback_complete()
                except Exception as e:
                    logger.error(f"Error in playback complete callback: {e}", exc_info=True)

    def stop(self):
        """Stop playback (if playing in background) and cleanup resources."""
        if not self._playing:
            # Still cleanup even if not playing
            if self._pyaudio:
                try:
                    self._pyaudio.terminate()
                    self._pyaudio = None
                except Exception as e:
                    logger.error(f"Error terminating PyAudio: {e}")
            return

        logger.info("Stopping audio playback...")
        self._playing = False

        if self._thread:
            self._thread.join(timeout=2.0)

        # Cleanup PyAudio on stop
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
                self._pyaudio = None
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")

    @property
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._playing


def list_audio_devices():
    """
    List all available audio devices.
    Useful for configuration and debugging.
    """
    try:
        p = pyaudio.PyAudio()

        logger.info("Available audio devices:")
        print("\nAvailable Audio Devices:")
        print("-" * 80)

        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            device_type = []

            if info['maxInputChannels'] > 0:
                device_type.append("INPUT")
            if info['maxOutputChannels'] > 0:
                device_type.append("OUTPUT")

            print(f"[{i}] {info['name']}")
            print(f"    Type: {', '.join(device_type)}")
            print(f"    Channels: In={info['maxInputChannels']}, Out={info['maxOutputChannels']}")
            print(f"    Sample Rate: {info['defaultSampleRate']} Hz")
            print()

        p.terminate()

    except Exception as e:
        logger.error(f"Error listing audio devices: {e}", exc_info=True)


def test_audio_output(duration: float = 1.0):
    """
    Test audio output with a simple tone.

    Args:
        duration: Duration of test tone in seconds
    """
    try:
        sample_rate = settings.SAMPLE_RATE
        frequency = 440.0  # A4 note

        # Generate test tone
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        tone = 0.3 * np.sin(2 * np.pi * frequency * t)

        # Create stereo (same tone on both channels for test)
        stereo_tone = np.column_stack((tone, tone))

        # Play
        player = AudioPlayer()
        player.play_stereo(stereo_tone, sample_rate, blocking=True)

        logger.info(f"Test tone played successfully ({frequency}Hz, {duration}s)")

    except Exception as e:
        logger.error(f"Error testing audio output: {e}", exc_info=True)


if __name__ == "__main__":
    # Quick test/utility script
    logging.basicConfig(level=logging.INFO)

    print("Audio Output Module Test")
    print("=" * 80)

    # List devices
    list_audio_devices()

    # Test output
    print("\nTesting audio output (440Hz tone for 1 second)...")
    test_audio_output(1.0)

    print("\nTest complete!")
