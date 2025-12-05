"""
Wake word detection module using Picovoice Porcupine.
Supports "Hey, Johnny" wake phrase with always-on listening.
"""

import logging
import threading
import struct
from typing import Optional, Callable
from pathlib import Path
import pyaudio

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    logging.warning("pvporcupine not installed. Wake word detection will not work.")

from teddy_ruxpin.config import settings
from teddy_ruxpin.utils import find_audio_device_by_name

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Always-on wake word detection using Picovoice Porcupine.
    Runs in a separate thread and triggers callback on detection.
    """

    def __init__(self, on_wake_word: Callable[[], None], wake_word_path: Path):
        """
        Initialize wake word detector.

        Args:
            on_wake_word: Callback function to execute when wake word is detected
            wake_word_path: Path to custom wake word .ppn file
        """
        self.on_wake_word = on_wake_word
        self.wake_word_path = wake_word_path
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._porcupine: Optional[pvporcupine.Porcupine] = None
        self._audio_stream: Optional[pyaudio.Stream] = None
        self._pyaudio: Optional[pyaudio.PyAudio] = None

        if not PORCUPINE_AVAILABLE:
            raise RuntimeError("pvporcupine library not installed")

        if not settings.PICOVOICE_ACCESS_KEY:
            raise ValueError("PICOVOICE_ACCESS_KEY not set in configuration")

    def start(self):
        """Start wake word detection in background thread."""
        if self._running:
            logger.warning("Wake word detector already running")
            return

        logger.info("Initializing wake word detector...")

        try:
            # Initialize Porcupine with custom wake word
            self._porcupine = pvporcupine.create(
                access_key=settings.PICOVOICE_ACCESS_KEY,
                keyword_paths=[str(self.wake_word_path)],
            )

            # Initialize PyAudio
            self._pyaudio = pyaudio.PyAudio()

            # Get input device by name (None = system default)
            device_index = None

            if settings.INPUT_DEVICE_NAME:
                # Find device by name
                device_index = find_audio_device_by_name(
                    self._pyaudio,
                    settings.INPUT_DEVICE_NAME,
                    "input"
                )
                if device_index is None:
                    logger.warning(f"Could not find input device '{settings.INPUT_DEVICE_NAME}', using default")

            # Get device info to check supported channels
            if device_index is None:
                device_info = self._pyaudio.get_default_input_device_info()
            else:
                device_info = self._pyaudio.get_device_info_by_index(device_index)

            # Try to use mono, but fall back to stereo if device doesn't support it
            max_input_channels = int(device_info['maxInputChannels'])
            if max_input_channels >= 1:
                # Device supports at least mono
                self._input_channels = 1
            else:
                raise RuntimeError(f"Input device has no input channels: {device_info['name']}")

            logger.info(f"Using audio device: {device_info['name']} (channels={self._input_channels})")

            # Open audio stream
            try:
                self._audio_stream = self._pyaudio.open(
                    rate=self._porcupine.sample_rate,
                    channels=self._input_channels,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=self._porcupine.frame_length,
                    input_device_index=device_index,
                )
            except OSError as e:
                # If mono fails, try stereo
                if self._input_channels == 1 and max_input_channels >= 2:
                    logger.warning(f"Mono input failed, trying stereo: {e}")
                    self._input_channels = 2
                    self._audio_stream = self._pyaudio.open(
                        rate=self._porcupine.sample_rate,
                        channels=self._input_channels,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=self._porcupine.frame_length,
                        input_device_index=device_index,
                    )
                else:
                    raise

            # Start detection thread
            self._running = True
            self._thread = threading.Thread(target=self._detection_loop, daemon=True)
            self._thread.start()

            logger.info(
                f"Wake word detector started (sample_rate={self._porcupine.sample_rate}Hz, "
                f"frame_length={self._porcupine.frame_length})"
            )

        except Exception as e:
            logger.error(f"Failed to start wake word detector: {e}", exc_info=True)
            self._cleanup()
            raise

    def stop(self):
        """Stop wake word detection and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping wake word detector...")
        self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)

        self._cleanup()
        logger.info("Wake word detector stopped")

    def _detection_loop(self):
        """Main detection loop running in background thread."""
        logger.info("Wake word detection loop started")

        try:
            while self._running:
                # Read audio frame
                pcm = self._audio_stream.read(
                    self._porcupine.frame_length,
                    exception_on_overflow=False
                )

                # Convert bytes to int16 array
                if self._input_channels == 1:
                    # Mono input - use as-is
                    pcm = struct.unpack_from("h" * self._porcupine.frame_length, pcm)
                else:
                    # Stereo input - extract left channel only
                    stereo_samples = struct.unpack_from("h" * (self._porcupine.frame_length * 2), pcm)
                    pcm = stereo_samples[::2]  # Take every other sample (left channel)

                # Process frame
                keyword_index = self._porcupine.process(pcm)

                if keyword_index >= 0:
                    logger.info("Wake word detected!")
                    try:
                        self.on_wake_word()
                    except Exception as e:
                        logger.error(f"Error in wake word callback: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in wake word detection loop: {e}", exc_info=True)
        finally:
            logger.info("Wake word detection loop ended")

    def _cleanup(self):
        """Clean up resources."""
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            self._audio_stream = None

        if self._porcupine:
            try:
                self._porcupine.delete()
            except Exception as e:
                logger.error(f"Error deleting Porcupine instance: {e}")
            self._porcupine = None

        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            self._pyaudio = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class MockWakeWordDetector:
    """
    Mock wake word detector for testing without Porcupine.
    Triggers on Enter key press.
    """

    def __init__(self, on_wake_word: Callable[[], None]):
        self.on_wake_word = on_wake_word
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start mock detector."""
        if self._running:
            return

        logger.info("Mock wake word detector started. Press Enter to simulate wake word.")
        self._running = True
        self._thread = threading.Thread(target=self._input_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop mock detector."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("Mock wake word detector stopped")

    def _input_loop(self):
        """Wait for Enter key to simulate wake word."""
        while self._running:
            try:
                input()  # Wait for Enter
                if self._running:
                    logger.info("Mock wake word detected (Enter pressed)")
                    self.on_wake_word()
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Error in mock input loop: {e}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
