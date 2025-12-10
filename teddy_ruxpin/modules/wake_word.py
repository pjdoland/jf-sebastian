"""
Wake word detection module using OpenWakeWord.
Supports custom wake phrases with always-on listening.
"""

import logging
import threading
import struct
import time
from typing import Optional, Callable
from pathlib import Path
from collections import deque
import pyaudio
import numpy as np

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    logging.warning("openwakeword not installed. Wake word detection will not work.")

from teddy_ruxpin.config import settings
from teddy_ruxpin.utils import find_audio_device_by_name

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """
    Always-on wake word detection using OpenWakeWord.
    Runs in a separate thread and triggers callback on detection.
    """

    def __init__(self, on_wake_word: Callable[[], None], wake_word_model_paths: list[Path]):
        """
        Initialize wake word detector.

        Args:
            on_wake_word: Callback function to execute when wake word is detected
            wake_word_model_paths: List of paths to custom wake word model files (.onnx or .tflite)
        """
        self.on_wake_word = on_wake_word
        self.wake_word_model_paths = wake_word_model_paths
        self._running = False
        self._paused = False  # Flag to pause detection without stopping the thread
        self._thread: Optional[threading.Thread] = None
        self._model: Optional[Model] = None
        self._audio_stream: Optional[pyaudio.Stream] = None
        self._pyaudio: Optional[pyaudio.PyAudio] = None

        # Audio buffer for rolling window detection (2 seconds = 32000 samples at 16kHz)
        self._audio_buffer: Optional[deque] = None

        # Debouncing to prevent multiple rapid detections
        self._last_detection_time: float = 0.0
        self._debounce_seconds: float = 2.0  # Minimum time between detections
        self._detection_threshold: float = 0.99

        if not OPENWAKEWORD_AVAILABLE:
            raise RuntimeError("openwakeword library not installed")

    def start(self):
        """Start wake word detection in background thread."""
        if self._running:
            logger.warning("Wake word detector already running")
            return

        logger.info("Initializing wake word detector...")

        try:
            # Initialize OpenWakeWord model
            # Convert Path objects to strings for OpenWakeWord
            model_paths = [str(path) for path in self.wake_word_model_paths]

            logger.info(f"Loading wake word models: {model_paths}")
            self._model = Model(
                wakeword_models=model_paths,
                inference_framework="onnx"
            )

            # Get required sample rate and chunk size from model
            self._sample_rate = 16000  # OpenWakeWord requires 16kHz
            self._chunk_size = 1280     # OpenWakeWord default chunk size (80ms at 16kHz)

            # Initialize audio buffer (2 seconds for proper model inference)
            buffer_samples = 32000  # 2 seconds at 16kHz
            self._audio_buffer = deque(maxlen=buffer_samples)

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
                    rate=self._sample_rate,
                    channels=self._input_channels,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=self._chunk_size,
                    input_device_index=device_index,
                )
            except OSError as e:
                # If mono fails, try stereo
                if self._input_channels == 1 and max_input_channels >= 2:
                    logger.warning(f"Mono input failed, trying stereo: {e}")
                    self._input_channels = 2
                    self._audio_stream = self._pyaudio.open(
                        rate=self._sample_rate,
                        channels=self._input_channels,
                        format=pyaudio.paInt16,
                        input=True,
                        frames_per_buffer=self._chunk_size,
                        input_device_index=device_index,
                    )
                else:
                    raise

            # Start detection thread
            self._running = True
            self._thread = threading.Thread(target=self._detection_loop, daemon=True)
            self._thread.start()

            logger.info(
                f"Wake word detector started (sample_rate={self._sample_rate}Hz, "
                f"chunk_size={self._chunk_size}, threshold={self._detection_threshold})"
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

    def pause(self):
        """Pause wake word detection (keeps running but skips processing)."""
        if not self._running:
            logger.warning("Cannot pause - detector not running")
            return

        if self._paused:
            logger.debug("Wake word detector already paused")
            return

        logger.debug("Pausing wake word detector")
        self._paused = True

    def resume(self):
        """Resume wake word detection after pausing."""
        if not self._running:
            logger.warning("Cannot resume - detector not running")
            return

        if not self._paused:
            logger.debug("Wake word detector not paused")
            return

        logger.debug("Resuming wake word detector")
        self._paused = False
        # Clear buffer when resuming to avoid detecting old audio
        if self._audio_buffer:
            self._audio_buffer.clear()
        if self._model:
            self._model.reset()

    def _detection_loop(self):
        """Main detection loop running in background thread."""
        logger.info("Wake word detection loop started")

        try:
            while self._running:
                # Skip processing if paused (but keep reading to prevent buffer overflow)
                if self._paused:
                    # Still read audio to prevent stream buffer overflow
                    self._audio_stream.read(
                        self._chunk_size,
                        exception_on_overflow=False
                    )
                    time.sleep(0.01)  # Small sleep to reduce CPU usage
                    continue

                # Read audio chunk
                pcm = self._audio_stream.read(
                    self._chunk_size,
                    exception_on_overflow=False
                )

                # Convert bytes to int16 array
                if self._input_channels == 1:
                    # Mono input - use as-is
                    audio_data = np.frombuffer(pcm, dtype=np.int16)
                else:
                    # Stereo input - extract left channel only
                    stereo_data = np.frombuffer(pcm, dtype=np.int16)
                    audio_data = stereo_data[::2]  # Take every other sample (left channel)

                # Add to rolling buffer
                self._audio_buffer.extend(audio_data)

                # Only process when buffer is full (have enough context)
                if len(self._audio_buffer) < self._audio_buffer.maxlen:
                    continue

                # Get buffered audio window
                audio_window = np.array(list(self._audio_buffer))

                # Use predict_clip for custom models (like easy-oww does)
                # This gives better results than streaming predict()
                predictions = self._model.predict_clip(audio_window, padding=1, chunk_size=1280)

                # Extract max score from all frames
                model_name = list(self._model.models.keys())[0]
                scores = [pred[model_name] for pred in predictions if model_name in pred]

                if scores:
                    max_score = max(scores)

                    # Check if wake word was detected
                    if max_score >= self._detection_threshold:
                        current_time = time.time()

                        # Debouncing: only trigger if enough time has passed since last detection
                        if current_time - self._last_detection_time >= self._debounce_seconds:
                            logger.info(
                                f"Wake word detected: {model_name} (score: {max_score:.3f} "
                                f">= threshold {self._detection_threshold:.2f})"
                            )
                            self._last_detection_time = current_time

                            try:
                                self.on_wake_word()
                            except Exception as e:
                                logger.error(f"Error in wake word callback: {e}", exc_info=True)

                            # Reset the model and clear buffer after detection to avoid multiple triggers
                            self._model.reset()
                            self._audio_buffer.clear()
                        else:
                            # Detection within debounce period - ignore it
                            logger.debug(f"Ignoring detection (debounce): score {max_score:.3f}")

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

        if self._model:
            # OpenWakeWord models don't need explicit cleanup
            self._model = None

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
    Mock wake word detector for testing without OpenWakeWord.
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
