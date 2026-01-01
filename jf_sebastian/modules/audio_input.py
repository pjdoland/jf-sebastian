"""
Audio input pipeline with microphone capture and voice activity detection.
Handles recording user speech after wake word detection.
"""

import logging
import time
import threading
import io
import wave
from typing import Optional, Callable
from collections import deque

import pyaudio
import webrtcvad
import numpy as np

from jf_sebastian.config import settings
from jf_sebastian.utils import find_audio_device_by_name

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Records audio from microphone with voice activity detection.
    Automatically detects when user stops speaking.
    """

    def __init__(self, on_speech_end: Callable[[bytes], None]):
        """
        Initialize audio recorder.

        Args:
            on_speech_end: Callback function receiving audio data when speech ends
        """
        self.on_speech_end = on_speech_end
        self._recording = False
        self._thread: Optional[threading.Thread] = None
        self._audio_stream: Optional[pyaudio.Stream] = None
        # Initialize PyAudio once and reuse it to avoid CoreAudio issues on macOS
        self._pyaudio = pyaudio.PyAudio()
        self._vad: Optional[webrtcvad.Vad] = None

        # Audio buffer for collected frames
        self._frames: deque = deque()

        # VAD frame buffer (30ms frames as required by WebRTC VAD)
        self._vad_frame_duration_ms = 30
        self._vad_frame_size = int(settings.SAMPLE_RATE * self._vad_frame_duration_ms / 1000)

        # Speech detection state
        self._speech_active = False
        self._silence_start_time: Optional[float] = None
        # Allow configurable silence duration and a minimum listen window to avoid early cutoff
        self._silence_threshold = settings.SPEECH_END_SILENCE_SECONDS
        self._min_listen_seconds = settings.MIN_LISTEN_SECONDS

        # Continuous conversation mode - if True, keep recording after speech ends
        self._continuous = False

        logger.info("Audio recorder initialized")

    def start_recording(self, initial_audio: Optional[bytes] = None, continuous: bool = False):
        """
        Start recording audio in background thread.

        Args:
            initial_audio: Optional audio bytes to prepend to recording (e.g., post-wake-word buffer)
                          Should be int16 audio at 16kHz
            continuous: If True, keep recording after speech ends (for multi-turn conversations)
        """
        if self._recording:
            logger.warning("Audio recorder already running")
            return

        logger.info(f"Starting audio recording (continuous={continuous})...")

        try:
            # Store continuous mode setting
            self._continuous = continuous

            # Initialize VAD
            self._vad = webrtcvad.Vad(settings.VAD_AGGRESSIVENESS)

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

            # Open audio stream with retry logic for macOS CoreAudio issues
            max_retries = 3
            retry_delay = 0.1

            for attempt in range(max_retries):
                try:
                    self._audio_stream = self._pyaudio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=settings.SAMPLE_RATE,
                        input=True,
                        frames_per_buffer=self._vad_frame_size,
                        input_device_index=device_index,
                    )
                    break  # Success, exit retry loop
                except OSError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Audio stream open failed (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise  # Final attempt failed, raise the error

            # Clear buffer
            self._frames.clear()

            # If initial audio provided, resample from 16kHz to 44.1kHz and add to buffer
            if initial_audio:
                initial_array = np.frombuffer(initial_audio, dtype=np.int16)
                # Resample from 16kHz to 44.1kHz
                from scipy import signal as scipy_signal
                num_samples = int(len(initial_array) * settings.SAMPLE_RATE / 16000)
                resampled = scipy_signal.resample(initial_array, num_samples)
                resampled_bytes = resampled.astype(np.int16).tobytes()
                self._frames.append(resampled_bytes)
                logger.info(f"Prepended {len(initial_array)} samples (16kHz) -> {num_samples} samples ({settings.SAMPLE_RATE}Hz) to recording")

            self._speech_active = False
            self._silence_start_time = None

            # Start recording thread
            self._recording = True
            self._thread = threading.Thread(target=self._recording_loop, daemon=True)
            self._thread.start()

            logger.info(f"Audio recording started (rate={settings.SAMPLE_RATE}Hz, vad_aggressiveness={settings.VAD_AGGRESSIVENESS})")

        except Exception as e:
            logger.error(f"Failed to start audio recording: {e}", exc_info=True)
            self._cleanup()
            raise

    def stop_recording(self):
        """Stop recording and return collected audio."""
        if not self._recording:
            return

        logger.info("Stopping audio recording...")
        self._recording = False

        # Only join thread if we're not calling from within the recording thread itself
        if self._thread and threading.current_thread() != self._thread:
            self._thread.join(timeout=2.0)
        elif self._thread:
            logger.debug("Skipping thread join (called from within recording thread)")

        # Get final audio data
        audio_data = self._get_audio_data()

        self._cleanup()
        logger.info(f"Audio recording stopped (captured {len(audio_data)} bytes)")

        return audio_data

    def _recording_loop(self):
        """Main recording loop with VAD."""
        logger.info("Recording loop started")
        start_time = time.time()

        try:
            while self._recording:
                # Check timeout
                if time.time() - start_time > settings.SILENCE_TIMEOUT:
                    logger.info(f"Recording timeout reached ({settings.SILENCE_TIMEOUT}s)")
                    should_continue = self._handle_speech_end()
                    if not should_continue:
                        break
                    # Reset start time for next turn
                    start_time = time.time()

                # Read audio frame
                try:
                    frame = self._audio_stream.read(
                        self._vad_frame_size,
                        exception_on_overflow=False
                    )
                except Exception as e:
                    logger.error(f"Error reading audio frame: {e}")
                    continue

                # Store frame
                self._frames.append(frame)

                # Check for speech activity
                is_speech = self._is_speech(frame)

                if is_speech:
                    # Speech detected
                    if not self._speech_active:
                        logger.debug("Speech started")
                        self._speech_active = True
                    self._silence_start_time = None

                else:
                    # Silence detected
                    if self._speech_active:
                        if self._silence_start_time is None:
                            self._silence_start_time = time.time()
                        elif (
                            time.time() - self._silence_start_time >= self._silence_threshold
                            and time.time() - start_time >= self._min_listen_seconds
                        ):
                            logger.info("Speech ended (silence detected)")
                            should_continue = self._handle_speech_end()
                            if not should_continue:
                                break
                            # Reset start time for next turn
                            start_time = time.time()

        except Exception as e:
            logger.error(f"Error in recording loop: {e}", exc_info=True)
        finally:
            logger.info("Recording loop ended")

    def _is_speech(self, frame: bytes) -> bool:
        """
        Check if audio frame contains speech using VAD.

        Args:
            frame: Audio frame (must be 10, 20, or 30ms)

        Returns:
            True if speech detected, False otherwise
        """
        try:
            return self._vad.is_speech(frame, settings.SAMPLE_RATE)
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return False

    def _handle_speech_end(self) -> bool:
        """
        Handle end of speech detection.

        Returns:
            True if should continue recording (continuous mode), False if should stop
        """
        audio_data = self._get_audio_data()

        if len(audio_data) > 0:
            try:
                self.on_speech_end(audio_data)
            except Exception as e:
                logger.error(f"Error in speech_end callback: {e}", exc_info=True)

        if self._continuous:
            # Continuous mode - reset state and continue recording
            logger.info("Continuous mode: resetting state for next turn")
            self._frames.clear()
            self._speech_active = False
            self._silence_start_time = None
            return True
        else:
            # Single-shot mode - stop recording
            self._recording = False
            return False

    def _get_audio_data(self) -> bytes:
        """Combine all frames into single audio data bytes."""
        if not self._frames:
            return b""

        return b"".join(self._frames)

    def _cleanup(self):
        """Clean up resources (but keep PyAudio instance for reuse)."""
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            self._audio_stream = None

        # Don't terminate PyAudio - we reuse it to avoid CoreAudio issues
        # It will be terminated when the application shuts down

        self._vad = None
        self._frames.clear()

    def cleanup_on_shutdown(self):
        """Final cleanup when application is shutting down."""
        self._cleanup()
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
                self._pyaudio = None
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")


def save_audio_to_wav(audio_data: bytes, filename: str, sample_rate: int = None):
    """
    Save raw audio data to WAV file for debugging.

    Args:
        audio_data: Raw PCM audio data (16-bit)
        filename: Output filename
        sample_rate: Sample rate (defaults to settings.SAMPLE_RATE)
    """
    if sample_rate is None:
        sample_rate = settings.SAMPLE_RATE

    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        logger.info(f"Audio saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving audio to {filename}: {e}")


def audio_data_to_wav_bytes(audio_data: bytes, sample_rate: int = None) -> bytes:
    """
    Convert raw audio data to WAV format bytes.

    Args:
        audio_data: Raw PCM audio data (16-bit)
        sample_rate: Sample rate (defaults to settings.SAMPLE_RATE)

    Returns:
        WAV formatted audio bytes
    """
    if sample_rate is None:
        sample_rate = settings.SAMPLE_RATE

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)

    return wav_buffer.getvalue()
