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
        self._stream_abandoned = False  # Track if we abandoned a stream without proper cleanup
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
        watchdog_timer = None

        def watchdog_timeout():
            """Watchdog callback - called if playback takes too long."""
            logger.error("WATCHDOG: Playback timeout reached, forcing stop")
            self._playing = False

        try:
            # Calculate expected duration and set watchdog (4x expected duration)
            expected_duration = len(stereo_audio) / sample_rate
            watchdog_duration = expected_duration * 4
            logger.debug(f"Setting watchdog timer for {watchdog_duration:.1f}s (4x {expected_duration:.1f}s expected duration)")
            watchdog_timer = threading.Timer(watchdog_duration, watchdog_timeout)
            watchdog_timer.daemon = True
            watchdog_timer.start()

            # Re-initialize PyAudio only if it was terminated (not if stream was abandoned)
            # Note: On macOS, creating multiple PyAudio instances causes CoreAudio conflicts
            # So we keep using the same instance even if we abandoned a stream
            if self._pyaudio is None:
                logger.warning("PyAudio was terminated, re-initializing...")
                self._pyaudio = pyaudio.PyAudio()

            if self._stream_abandoned:
                logger.info("Previous stream was abandoned, waiting for macOS to release audio resources...")
                # Give macOS CoreAudio time to release the abandoned stream
                # This is a workaround for PyAudio not being able to open new streams
                # immediately after abandoning one on macOS
                # Increased to 5s as 3s was still timing out on macOS
                time.sleep(5.0)
                self._stream_abandoned = False
                logger.info("Proceeding with stream open after delay")

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
            else:
                logger.debug("OUTPUT_DEVICE_NAME not set, using system default audio device")

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
                import librosa

                # Resample each channel using high-quality resampling
                left_resampled = librosa.resample(
                    stereo_audio[:, 0].astype(np.float32),
                    orig_sr=sample_rate,
                    target_sr=device_sample_rate,
                    res_type='kaiser_best'
                )
                right_resampled = librosa.resample(
                    stereo_audio[:, 1].astype(np.float32),
                    orig_sr=sample_rate,
                    target_sr=device_sample_rate,
                    res_type='kaiser_best'
                )

                # Combine back to stereo
                stereo_audio = np.column_stack((left_resampled, right_resampled))
                sample_rate = device_sample_rate

            # Clip to valid range and convert to int16
            stereo_audio = np.clip(stereo_audio, -1.0, 1.0)
            audio_int16 = (stereo_audio * 32767).astype(np.int16)

            # Open output stream with timeout protection (stream.open can block on macOS)
            stream = None
            open_success = False

            def open_stream_thread():
                nonlocal open_success, stream
                try:
                    logger.info("Opening audio stream...")
                    stream = self._pyaudio.open(
                        format=pyaudio.paInt16,
                        channels=2,  # Stereo
                        rate=sample_rate,
                        output=True,
                        output_device_index=device_index,
                        frames_per_buffer=1024,
                    )
                    logger.info("Audio stream opened successfully")
                    open_success = True
                except Exception as e:
                    logger.error(f"Error opening stream: {e}")

            opener = threading.Thread(target=open_stream_thread, daemon=True)
            opener.start()
            opener.join(timeout=3.0)  # Wait up to 3 seconds for stream open

            if not open_success or stream is None:
                logger.error("Stream open timed out or failed after 3s")
                raise RuntimeError("Failed to open audio stream (timeout or error)")

            # Explicitly start the stream (should already be started, but be explicit)
            if not stream.is_active():
                logger.info("Stream not active, starting it explicitly")
                stream.start_stream()

            # Play audio in chunks to allow interruption
            # Write in 0.1 second chunks so we can check stop flag
            chunk_size = int(sample_rate * 0.1 * 2)  # 0.1s * 2 channels
            audio_bytes = audio_int16.tobytes()
            total_bytes = len(audio_bytes)
            bytes_per_frame = 4  # 2 bytes per sample * 2 channels

            # Calculate expected playback duration for timeout detection
            expected_duration = len(stereo_audio) / sample_rate
            playback_start_time = time.time()

            offset = 0
            chunks_written = 0
            last_progress_time = playback_start_time

            while offset < total_bytes and self._playing:
                # Check for hung playback (more than 3x expected duration)
                elapsed = time.time() - playback_start_time
                if elapsed > expected_duration * 3:
                    logger.error(f"Playback timeout: {elapsed:.1f}s elapsed, expected {expected_duration:.1f}s")
                    break

                # Check for stalled write (no progress in 5 seconds)
                if time.time() - last_progress_time > 5.0:
                    logger.error(f"Playback stalled: no progress for 5s at chunk {chunks_written}, offset {offset}/{total_bytes}")
                    break

                # Write next chunk
                chunk_end = min(offset + chunk_size * bytes_per_frame, total_bytes)

                # Log every 100 chunks to track progress without spamming
                if chunks_written % 100 == 0:
                    logger.debug(f"Writing chunk {chunks_written}, offset {offset}/{total_bytes}, elapsed {elapsed:.1f}s")

                # Log first chunk write attempt
                if chunks_written == 0:
                    logger.info(f"Starting to write audio data ({total_bytes} bytes)...")

                try:
                    stream.write(audio_bytes[offset:chunk_end])
                    offset = chunk_end
                    chunks_written += 1
                    last_progress_time = time.time()

                    # Log first chunk success
                    if chunks_written == 1:
                        logger.info(f"First chunk written successfully")

                except Exception as write_error:
                    logger.error(f"Error writing audio chunk {chunks_written}: {write_error}")
                    break

            write_duration = time.time() - playback_start_time
            logger.info(f"Wrote {chunks_written} chunks, {offset}/{total_bytes} bytes in {write_duration:.2f}s")

            # Wait a moment to ensure all audio has been played from the buffer
            # This helps prevent stream close timeout on macOS
            time.sleep(0.2)

            # Close stream with timeout protection
            # Use a separate thread because stream.stop_stream() can block indefinitely on macOS
            close_success = False
            def close_stream_thread():
                nonlocal close_success, stream
                try:
                    logger.info("Stopping audio stream...")
                    stream.stop_stream()
                    logger.info("Audio stream stopped, closing...")
                    stream.close()
                    logger.info("Audio stream closed")
                    close_success = True
                except Exception as e:
                    logger.error(f"Error in stream close thread: {e}")

            closer = threading.Thread(target=close_stream_thread, daemon=True)
            closer.start()
            closer.join(timeout=10.0)  # Wait up to 10 seconds for clean close (macOS can be slow)

            if not close_success:
                logger.warning("Stream close timed out after 10s, abandoning stream (may leak resources)")
                self._stream_abandoned = True
                # Note: We don't terminate PyAudio here because terminate() can block for 20+ seconds on macOS,
                # which is worse than just abandoning the stream. The 3-second delay in the next playback
                # attempt (see line 126) should give macOS enough time to release resources.
            else:
                logger.info("Stream closed cleanly")

            stream = None

            if self._playing:
                logger.info("Audio playback completed")
            else:
                logger.info("Audio playback stopped (interrupted)")

        except Exception as e:
            logger.error(f"Error during audio playback: {e}", exc_info=True)

        finally:
            # Cancel watchdog timer if it's still running
            if watchdog_timer:
                watchdog_timer.cancel()
                logger.debug("Watchdog timer cancelled")

            try:
                # Clean up stream if it's still open
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception as cleanup_error:
                        logger.error(f"Stream cleanup error: {cleanup_error}")
            finally:
                # GUARANTEE flag is cleared (nested finally)
                self._playing = False
                logger.debug(f"Playback flag cleared")

            # Call completion callback
            if self.on_playback_complete:
                try:
                    self.on_playback_complete()
                except Exception as e:
                    logger.error(f"Error in playback complete callback: {e}", exc_info=True)

    def stop(self):
        """Stop playback (if playing in background)."""
        if not self._playing:
            return

        logger.info("Stopping audio playback...")
        self._playing = False

        if self._thread:
            self._thread.join(timeout=2.0)

    def cleanup(self):
        """Cleanup resources - call this when shutting down the application."""
        logger.info("Cleaning up AudioPlayer resources...")

        # Stop any active playback first
        self.stop()

        # Terminate PyAudio
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
                self._pyaudio = None
                logger.info("PyAudio terminated successfully")
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")

    def __del__(self):
        """Destructor - ensure PyAudio is terminated."""
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except:
                pass  # Ignore errors during cleanup

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
