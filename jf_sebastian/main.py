"""
J.F. Sebastian - Main application for the AI conversation system.
"I make friends. They're toys. My friends are toys. I make them."

Integrates all modules and manages conversation flow.
"""

import logging
import sys
import time
import signal
import os
from pathlib import Path
from typing import Optional
import numpy as np
import psutil

from jf_sebastian.config import settings
from personalities import get_personality
from jf_sebastian.modules.state_machine import StateMachine, ConversationState
from jf_sebastian.modules.wake_word import WakeWordDetector
from jf_sebastian.modules.audio_input import AudioRecorder, save_audio_to_wav
from jf_sebastian.modules.speech_to_text import SpeechToText
from jf_sebastian.modules.conversation import ConversationEngine
from jf_sebastian.modules.text_to_speech import TextToSpeech
from jf_sebastian.devices import DeviceRegistry
from jf_sebastian.utils.audio_utils import save_stereo_wav
from jf_sebastian.utils.async_file_utils import save_async
from jf_sebastian.modules.audio_output import AudioPlayer
from jf_sebastian.modules.filler_phrases import FillerPhraseManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('jf_sebastian.log')
    ]
)

logger = logging.getLogger(__name__)


class TeddyRuxpinApp:
    """
    Main application class for animatronic AI conversation system.
    Orchestrates all modules and manages conversation flow.
    """

    def __init__(self):
        """Initialize the application."""
        logger.info("=" * 80)
        logger.info("J.F. Sebastian - Animatronic AI Conversation System")
        logger.info('"I make friends. They\'re toys. My friends are toys."')
        logger.info("=" * 80)

        # Load personality
        try:
            self.personality = get_personality(settings.PERSONALITY)
            logger.info(f"Personality: {self.personality.name}")
            logger.info(f"Wake word: Hey {self.personality.name}")
        except ValueError as e:
            logger.error(f"Failed to load personality: {e}")
            raise

        # Validate configuration
        errors = settings.validate()
        if errors:
            logger.error("Configuration errors:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid configuration")

        # Create debug directories if needed
        settings.create_debug_dirs()

        # Initialize state machine
        self.state_machine = StateMachine()

        # Initialize modules
        logger.info("Initializing modules...")

        self.wake_word_detector = WakeWordDetector(
            on_wake_word=self._on_wake_word,
            wake_word_model_paths=self.personality.wake_word_model_paths
        )
        self.audio_recorder = AudioRecorder(on_speech_end=self._on_speech_end)
        self.speech_to_text = SpeechToText()
        self.conversation_engine = ConversationEngine(system_prompt=self.personality.system_prompt)
        self.text_to_speech = TextToSpeech(
            voice=self.personality.tts_voice,
            speed=self.personality.tts_speed,
            style_instruction=self.personality.tts_style
        )
        self.output_device = DeviceRegistry.create(settings.OUTPUT_DEVICE_TYPE)
        logger.info(f"Output device: {self.output_device.device_name}")

        # Validate device-specific settings
        device_errors = self.output_device.validate_settings()
        if device_errors:
            logger.error("Device configuration errors:")
            for error in device_errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid device configuration")
        self.audio_player = AudioPlayer(on_playback_complete=self._on_playback_complete)

        # Initialize filler phrase manager with personality-specific directory, phrases, and device type
        # This pre-loads all filler audio into memory for instant access
        self.filler_manager = FillerPhraseManager(
            self.personality.filler_audio_dir,
            self.personality.filler_phrases,
            settings.OUTPUT_DEVICE_TYPE
        )
        if self.filler_manager.has_fillers:
            logger.info(f"Filler phrases ready ({len(self.filler_manager.filler_cache)} phrases pre-loaded)")
        else:
            logger.warning("No filler phrases found - run scripts/generate_fillers.py to create them")

        # Register state callbacks
        self._register_state_callbacks()

        # Pre-warm RVC model if enabled (loads model into memory for faster first response)
        # TEMPORARILY DISABLED: Heavy torch/rvc imports cause slow startup
        # TODO: Re-enable with lazy imports or background thread
        # if self.personality.rvc_enabled:
        #     logger.info("Pre-warming RVC model...")
        #     try:
        #         from jf_sebastian.modules.rvc_processor import RVCProcessor
        #         self._rvc_processor = RVCProcessor(device=settings.RVC_DEVICE)
        #         if self._rvc_processor.available:
        #             model_path = self.personality.rvc_model_path
        #             if model_path:
        #                 logger.info(f"RVC model pre-warmed: {model_path}")
        #             else:
        #                 logger.warning("RVC model path not found, skipping pre-warm")
        #         else:
        #             logger.warning("RVC processor not available, skipping pre-warm")
        #     except Exception as e:
        #         logger.warning(f"Failed to pre-warm RVC model: {e}")

        # Running flag
        self._running = False
        self._selected_filler = None  # Store pre-selected filler for playback
        self._wake_paused_for_playback = False
        self._sequential_playback_active = False  # Track if we're playing queued chunks

        logger.info("Application initialized successfully")

    def _register_state_callbacks(self):
        """Register callbacks for state transitions."""
        self.state_machine.register_callback(
            ConversationState.LISTENING,
            self._on_enter_listening
        )
        self.state_machine.register_callback(
            ConversationState.PROCESSING,
            self._on_enter_processing
        )
        self.state_machine.register_callback(
            ConversationState.SPEAKING,
            self._on_enter_speaking
        )
        self.state_machine.register_callback(
            ConversationState.IDLE,
            self._on_enter_idle
        )

    def start(self):
        """Start the application."""
        if self._running:
            logger.warning("Application already running")
            return

        logger.info(f"Starting {self.personality.name} AI system...")
        self._running = True

        # Start wake word detection
        self.wake_word_detector.start()

        logger.info("=" * 80)
        logger.info(f"System ready! Say 'Hey, {self.personality.name}' to start talking.")
        logger.info("Press Ctrl+C to exit.")
        logger.info("=" * 80)

        # Main loop
        try:
            loop_iterations = 0
            while self._running:
                time.sleep(0.1)
                loop_iterations += 1

                # Validate state every 5 seconds (50 iterations * 0.1s)
                if loop_iterations % 50 == 0:
                    self._validate_and_recover_state()

        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")

        finally:
            self.stop()

    def stop(self):
        """Stop the application and clean up resources."""
        if not self._running:
            return

        logger.info(f"Stopping {self.personality.name} AI system...")
        self._running = False

        # Stop modules
        self.wake_word_detector.stop()
        self.audio_player.stop()

        # Cleanup audio resources
        self.audio_player.cleanup()

        logger.info("Application stopped")

    # -------------------------------------------------------------------------
    # Wake Word Detection
    # -------------------------------------------------------------------------

    def _on_wake_word(self):
        """Handle wake word detection."""
        logger.info("Wake word detected!")

        # Only respond to wake word when in IDLE state (ignore if already in an interaction)
        if self.state_machine.state != ConversationState.IDLE:
            logger.warning(f"Ignoring wake word - already in {self.state_machine.state.name} state")
            return

        # Transition to LISTENING state
        self.state_machine.transition_to(ConversationState.LISTENING, trigger="wake_word")

    # -------------------------------------------------------------------------
    # State Callbacks
    # -------------------------------------------------------------------------

    def _on_enter_listening(self):
        """Handle entering LISTENING state."""
        logger.info("Entering LISTENING state - recording audio...")

        # Pause wake word detector while listening to user (and for rest of interaction)
        # (Will already be paused if continuing conversation)
        self._pause_wake_for_playback()

        # Only start recording if not already recording (new conversation from IDLE)
        # When continuing conversation (from SPEAKING), recorder is already running
        if not self.audio_recorder._recording:
            # New conversation - use post-wake-word audio buffer
            post_wake_audio = self.wake_word_detector.get_post_wake_audio()
            logger.debug("Starting new conversation with post-wake audio buffer")
            self.audio_recorder.start_recording(initial_audio=post_wake_audio)
        else:
            # Continuing conversation - recorder is already running, just let it continue
            logger.debug("Continuing conversation - recorder already running")

    def _on_enter_processing(self):
        """Handle entering PROCESSING state."""
        logger.info("Entering PROCESSING state - transcribing and generating response...")

        # Filler will be added to playback queue in _process_and_speak
        # (no longer playing it separately to avoid race conditions)

        # Processing will be handled by _on_speech_end callback

    def _on_enter_speaking(self):
        """Handle entering SPEAKING state."""
        logger.info("Entering SPEAKING state - playing response...")

        # Speaking will be handled by _process_and_speak method

    def _on_enter_idle(self):
        """Handle entering IDLE state."""
        logger.info("Entering IDLE state - waiting for wake word...")

        # Resume wake word detector
        self._resume_wake_after_playback()

        # Check if conversation should be cleared
        if self.conversation_engine.time_since_last_interaction > settings.CONVERSATION_TIMEOUT:
            logger.info("Clearing conversation history due to timeout")
            self.conversation_engine.clear_history()

    # -------------------------------------------------------------------------
    # Audio Input Processing
    # -------------------------------------------------------------------------

    def _on_speech_end(self, audio_data: bytes):
        """
        Handle end of speech detection.

        Args:
            audio_data: Recorded audio data
        """
        logger.info(f"Speech ended, captured {len(audio_data)} bytes")

        # Check if audio is too short (timeout without meaningful speech)
        # At 16kHz, MIN_LISTEN_SECONDS * 16000 * 2 bytes = minimum expected bytes
        min_bytes = int(settings.MIN_LISTEN_SECONDS * 16000 * 2)
        if len(audio_data) < min_bytes:
            logger.info(f"Audio too short ({len(audio_data)} < {min_bytes} bytes), ending conversation")
            self.state_machine.transition_to(ConversationState.IDLE, trigger="silence_timeout")
            return

        # Save debug audio if enabled (async - non-blocking)
        if settings.SAVE_DEBUG_AUDIO:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = settings.DEBUG_AUDIO_PATH / f"input_{timestamp}.wav"
            save_async(save_audio_to_wav, audio_data, str(filename))

        # Select filler FIRST (before state transition) so we can pass its context to the LLM
        filler_context = None
        if self.filler_manager.has_fillers:
            filler_result = self.filler_manager.get_random_filler()
            if filler_result:
                self._selected_filler = filler_result  # Store for later playback
                filler_context = filler_result[2]  # Extract text
                logger.info(f"Selected filler context for LLM: {filler_context[:50]}...")

        # Transition to PROCESSING state (this will trigger _on_enter_processing which plays the filler)
        self.state_machine.transition_to(ConversationState.PROCESSING, trigger="speech_end")

        # Process audio in background to not block
        self._process_and_speak(audio_data, filler_context=filler_context)

    def _process_and_speak(self, audio_data: bytes, filler_context: Optional[str] = None):
        """
        Process audio and generate response with sentence-by-sentence streaming.

        Args:
            audio_data: Recorded audio data
            filler_context: Text of the filler phrase being played (for seamless transition)
        """
        try:
            # Step 1: Transcribe audio
            logger.info("Step 1: Transcribing speech...")
            transcript = self.speech_to_text.transcribe_with_retry(audio_data)

            if not transcript:
                logger.warning("Transcription failed or empty")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="transcription_failed")
                return

            logger.info(f"Transcript: \"{transcript}\"")

            # Step 2-4: Stream LLM → process each sentence through TTS+RVC → queue for playback
            logger.info("Step 2: Streaming response with sentence-by-sentence pipeline...")

            # Build context prompt if we have filler
            if filler_context:
                context_prompt = f"""[IMPORTANT CONTEXT: You just said this to the customer while thinking: "{filler_context}"]

Your response must create a seamless, natural continuation. Follow these guidelines:
1. Pick up grammatically and syntactically where the filler left off
2. If the filler ended with "Now..." or "So..." or "Alright..." - continue directly without repeating these words
3. Match the tone and energy of how you ended the filler phrase
4. Don't acknowledge or reference that you were doing something else - stay in character
5. Make it sound like one continuous thought, not two separate statements

Now respond to their question naturally, as if your filler phrase was the beginning of this same thought."""
            else:
                context_prompt = None

            # Stream audio chunks with true async processing
            # Process chunks in parallel with playback to eliminate gaps
            import threading
            import queue

            full_response_text = ""
            chunk_num = 0
            first_chunk = True
            chunks_attempted = 0  # Track chunk attempts for recovery

            # Save all chunks for debug
            debug_chunks = []

            # Queue for chunks ready to play
            playback_queue = queue.Queue()
            playback_done = threading.Event()
            playback_error = None

            def playback_worker():
                """Background thread that plays chunks sequentially from the queue."""
                nonlocal playback_error
                try:
                    chunk_count = 0
                    is_first_real_chunk = True  # Track first non-filler chunk

                    while True:
                        # Get next chunk from queue (blocks until available)
                        item = playback_queue.get()

                        if item is None:  # Sentinel to stop
                            logger.info("Playback worker finishing")
                            break

                        # Unpack with optional chunk_type
                        if len(item) == 4:
                            stereo_audio, sample_rate, chunk_id, chunk_type = item
                        else:
                            stereo_audio, sample_rate, chunk_id = item
                            chunk_type = "chunk"

                        chunk_count += 1

                        # Transition to SPEAKING state before first real chunk (after filler)
                        if chunk_type == "chunk" and is_first_real_chunk:
                            logger.info(f"First response chunk ready, transitioning to SPEAKING state")
                            self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_ready")
                            is_first_real_chunk = False

                        # Play this item (blocks until complete)
                        logger.info(f"{chunk_type.capitalize()} {chunk_id}: Playing NOW...")
                        logger.debug(f"{chunk_type.capitalize()} {chunk_id}: Calling play_stereo (audio_player.is_playing={self.audio_player.is_playing})")

                        # Use preroll only for first item (filler)
                        preroll = 0 if chunk_type == "chunk" else None

                        success = self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=True, preroll_ms=preroll)

                        logger.debug(f"{chunk_type.capitalize()} {chunk_id}: play_stereo returned {success}")
                        if not success:
                            logger.warning(f"{chunk_type.capitalize()} {chunk_id}: Playback failed - DROPPING")
                        else:
                            logger.info(f"{chunk_type.capitalize()} {chunk_id}: Playback complete")

                        playback_queue.task_done()

                    logger.info(f"Playback complete: {chunk_count} items played")
                except Exception as e:
                    playback_error = e
                    logger.error(f"Playback worker error: {e}", exc_info=True)
                finally:
                    playback_done.set()

            # Mark sequential playback as active (disables premature IDLE transitions)
            self._sequential_playback_active = True

            # Start playback worker thread
            playback_thread = threading.Thread(target=playback_worker, daemon=True)
            playback_thread.start()

            # Add filler to queue FIRST (before any chunks) if available
            if self._selected_filler:
                stereo_audio, sample_rate, _ = self._selected_filler
                logger.info("Adding filler to playback queue (will play before response chunks)")
                # Wait 0.5 seconds before adding filler for natural pause
                time.sleep(0.5)
                playback_queue.put((stereo_audio, sample_rate, "filler", "filler"))
                self._pause_wake_for_playback()  # Pause wake detection during entire playback sequence
            else:
                # No filler, transition to SPEAKING immediately when first chunk plays
                pass

            # Stream LLM response and process each sentence
            for sentence_text, is_final in self.conversation_engine.generate_response_streaming(
                transcript,
                additional_context=context_prompt
            ):
                if is_final:
                    logger.info("LLM streaming complete")
                    break

                if not sentence_text.strip():
                    continue

                chunk_num += 1
                full_response_text += sentence_text + " "
                logger.info(f"Chunk {chunk_num}: Processing sentence: \"{sentence_text}\"")

                # Process this sentence through TTS
                logger.info(f"Chunk {chunk_num}: Synthesizing speech...")
                voice_audio_mp3 = self.text_to_speech.synthesize_with_retry(sentence_text)

                if not voice_audio_mp3:
                    logger.warning(f"Chunk {chunk_num}: TTS failed, skipping")
                    chunks_attempted += 1
                    # Force transition after 3 failures to avoid 10-second silence
                    if chunks_attempted >= 3 and first_chunk:
                        logger.warning("Multiple TTS failures, transitioning to SPEAKING anyway")
                        self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_partial")
                        first_chunk = False
                    continue

                # Process through RVC (happens in parallel with playback of previous chunk!)
                logger.info(f"Chunk {chunk_num}: Converting with RVC...")
                result = self.output_device.create_output(voice_audio_mp3, sentence_text, self.personality)

                if not result:
                    logger.warning(f"Chunk {chunk_num}: RVC processing failed, skipping")
                    chunks_attempted += 1
                    # Force transition after 3 failures to avoid 10-second silence
                    if chunks_attempted >= 3 and first_chunk:
                        logger.warning("Multiple RVC failures, transitioning to SPEAKING anyway")
                        self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_partial")
                        first_chunk = False
                    continue

                stereo_audio, sample_rate = result
                logger.info(f"Chunk {chunk_num}: Ready! ({len(stereo_audio)} samples @ {sample_rate}Hz)")

                # Save for debug
                if settings.SAVE_DEBUG_AUDIO:
                    debug_chunks.append((stereo_audio.copy(), sample_rate))

                if first_chunk:
                    logger.info(f"Chunk {chunk_num}: First chunk ready")
                    first_chunk = False

                # Queue chunk for playback (will play in sequence after filler)
                logger.info(f"Chunk {chunk_num}: Queuing for playback...")
                playback_queue.put((stereo_audio, sample_rate, chunk_num, "chunk"))

            # Signal playback worker to finish after all chunks
            playback_queue.put(None)

            # Wait for all chunks to finish playing
            logger.info("Waiting for all chunks to finish playing...")
            playback_done.wait()

            if playback_error:
                raise playback_error

            if chunk_num == 0:
                logger.warning("No audio chunks generated")
                self._sequential_playback_active = False
                self.state_machine.transition_to(ConversationState.IDLE, trigger="generation_failed")
                return

            logger.info(f"Streaming playback complete: {chunk_num} chunks, full text: \"{full_response_text.strip()}\"")

            # All chunks done - transition to LISTENING to continue conversation
            # If no speech is detected within SILENCE_TIMEOUT, the audio recorder will timeout
            # and we'll transition to IDLE in _on_speech_end
            self._sequential_playback_active = False
            self.state_machine.transition_to(ConversationState.LISTENING, trigger="continue_conversation")

            # Save debug audio (concatenated version for comparison)
            if settings.SAVE_DEBUG_AUDIO and debug_chunks:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = settings.DEBUG_AUDIO_PATH / f"output_{timestamp}.wav"
                sample_rate = debug_chunks[0][1]
                concatenated = np.concatenate([chunk[0] for chunk in debug_chunks], axis=0)
                save_async(save_stereo_wav, concatenated, sample_rate, str(filename))

        except Exception as e:
            logger.error(f"Error in processing pipeline: {e}", exc_info=True)
            self._sequential_playback_active = False
            self.state_machine.transition_to(ConversationState.IDLE, trigger="error")

    def _play_filler(self):
        """DEPRECATED - Filler is now added to playback queue instead."""
        # This method is no longer used - filler is added directly to the playback queue
        # in _process_and_speak to ensure sequential playback without race conditions
        pass

    def _validate_and_recover_state(self) -> bool:
        """
        Validate system state and attempt recovery if stuck.
        Called periodically (every 5 seconds) to detect and fix inconsistencies.

        Returns:
            True if state is valid or was recovered
        """
        # Check 1: Wake paused in IDLE state
        if self._wake_paused_for_playback and self.state_machine.state == ConversationState.IDLE:
            logger.warning("RECOVERY: Wake detector stuck paused in IDLE")
            self._resume_wake_after_playback()

        # Check 2: Audio playing in IDLE state (skip during sequential playback)
        if self.audio_player.is_playing and self.state_machine.state == ConversationState.IDLE and not self._sequential_playback_active:
            logger.warning("RECOVERY: Audio playing in IDLE state - stopping")
            self.audio_player.stop()

        # Check 3: Stuck in PROCESSING (30 second timeout)
        # Skip this check during sequential playback - we're actively playing chunks
        # Normal processing with filler can take 20+ seconds:
        # - Transcription: 1-2s
        # - Filler playback: 10-20s
        # - LLM streaming: 2-5s
        # - TTS + RVC for first chunk: 3-5s
        if self.state_machine.state == ConversationState.PROCESSING and not self._sequential_playback_active:
            # Calculate time in state
            time_in_state = time.time() - getattr(self.state_machine, '_last_transition_time', time.time())
            if time_in_state > 30.0:
                logger.error(f"RECOVERY: Stuck in PROCESSING for {time_in_state:.1f}s - forcing IDLE")
                self.audio_player.stop()
                self.state_machine.transition_to(ConversationState.IDLE, trigger="recovery_timeout")

        return True

    def _on_playback_complete(self):
        """Handle playback completion."""
        logger.info("Playback complete callback called")

        # Ignore this callback during sequential playback - the main thread handles IDLE transition
        if self._sequential_playback_active:
            logger.debug("Sequential playback active, ignoring premature callback")
            return

        # Resume wake word detector after all playback finishes
        self._resume_wake_after_playback()

        # Return to IDLE state
        self.state_machine.transition_to(ConversationState.IDLE, trigger="playback_complete")

    def _pause_wake_for_playback(self):
        """Pause wake-word detection while audio is playing to avoid self-trigger."""
        if not self._wake_paused_for_playback:
            try:
                self.wake_word_detector.pause()
            except Exception as e:
                logger.error(f"Error pausing wake word detector: {e}")
            self._wake_paused_for_playback = True

    def _resume_wake_after_playback(self):
        """Resume wake-word detection after playback completes."""
        if self._wake_paused_for_playback:
            try:
                self.wake_word_detector.resume()
            except Exception as e:
                logger.error(f"Error resuming wake word detector: {e}")
            self._wake_paused_for_playback = False


def kill_existing_instances():
    """Kill any other running instances of this program."""
    current_pid = os.getpid()
    current_process = psutil.Process(current_pid)
    current_cmdline = ' '.join(current_process.cmdline())

    killed_count = 0
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Skip if it's the current process
            if process.pid == current_pid:
                continue

            # Check if this is a python process running jf_sebastian.main
            cmdline = process.cmdline()
            if cmdline and 'python' in cmdline[0].lower():
                cmdline_str = ' '.join(cmdline)
                if 'jf_sebastian.main' in cmdline_str or 'jf_sebastian/main.py' in cmdline_str:
                    logger.warning(f"Killing existing instance (PID {process.pid}): {cmdline_str}")
                    process.terminate()

                    # Wait up to 2 seconds for graceful termination
                    try:
                        process.wait(timeout=2)
                    except psutil.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        logger.warning(f"Force killing PID {process.pid}")
                        process.kill()

                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process may have already terminated or we don't have permission
            pass

    if killed_count > 0:
        logger.info(f"Killed {killed_count} existing instance(s)")
        # Brief pause to ensure resources are released
        time.sleep(0.5)


def main():
    """Main entry point."""
    # Kill any existing instances before starting
    kill_existing_instances()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        logger.info("Interrupt received, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Create and start application
    try:
        app = TeddyRuxpinApp()
        app.start()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
