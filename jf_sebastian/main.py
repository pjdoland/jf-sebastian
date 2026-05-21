"""
J.F. Sebastian - Main application for the AI conversation system.
"I make friends. They're toys. My friends are toys. I make them."

Integrates all modules and manages conversation flow.
"""

import logging
import logging.handlers
import sys
import time
import signal
import os
import queue
import threading
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
from jf_sebastian.utils.audio_utils import save_stereo_wav, calculate_rms, contains_speech
from jf_sebastian.utils.async_file_utils import save_async
from jf_sebastian.modules.audio_output import AudioPlayer
from jf_sebastian.modules.filler_phrases import FillerPhraseManager
from jf_sebastian.utils.context_provider import warm_news_cache, warm_weather_cache
from jf_sebastian.utils.heartbeat import Heartbeat
from jf_sebastian.modules.scheduler import (
    ProactiveScheduler,
    ScheduledEvent,
    load_scheduled_events,
    parse_time_or_none,
)

# Configure logging. Use RotatingFileHandler so the log file can't grow unbounded
# (important for unattended deployments under the supervisor — see scripts/supervisor.py).
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            'jf_sebastian.log', maxBytes=10 * 1024 * 1024, backupCount=5
        ),
    ],
)

logger = logging.getLogger(__name__)

# Common Whisper hallucinations when transcribing silence or background noise
# These phrases should be filtered out before processing
WHISPER_SILENCE_HALLUCINATIONS = {
    # Common closing phrases
    'thank you', 'thanks', 'thank you for watching', 'thanks for watching',
    'goodbye', 'bye', 'bye bye', 'see you', 'see you next time', 'see you later',

    # Common filler phrases that Whisper returns for silence
    'you', 'the', 'okay', 'oh', 'so', 'well', 'and', 'but', 'yeah', 'yes', 'no',

    # Music/video-related (common in training data)
    'subscribe', 'like and subscribe', 'please subscribe',

    # Empty or punctuation-only
    '', '.', '...', '..', '?', '!',

    # Single letters or very short
    'a', 'i', 'o',
}


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

        # Resolve auto-detected settings
        settings.resolve_rvc_device()

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

        # Warm up RVC if personality uses it (eliminates first-use delay)
        if self.personality.rvc_enabled:
            logger.info(f"Warming up RVC for personality '{self.personality.name}'...")
            self.output_device.audio_processor.warmup_rvc(self.personality)

        # Pre-fetch weather + news in background so first conversation doesn't block
        warm_weather_cache()
        warm_news_cache()

        # Liveness heartbeat for the supervisor (no-op if HEARTBEAT_FILE unset)
        self.heartbeat: Optional[Heartbeat] = None
        if settings.HEARTBEAT_FILE:
            self.heartbeat = Heartbeat(settings.HEARTBEAT_FILE, settings.HEARTBEAT_INTERVAL)
            self.heartbeat.start()

        # Initialize proactive scheduler from per-personality scheduled_events.yaml.
        # If either QUIET_HOURS_* env var is set, both come from env (atomically);
        # otherwise both come from the YAML. This avoids the surprise of mixing
        # an env-var start with a YAML end (or vice versa).
        self.scheduler: Optional[ProactiveScheduler] = None
        if settings.SCHEDULER_ENABLED:
            events, yaml_quiet_start, yaml_quiet_end = load_scheduled_events(
                self.personality.scheduled_events_path
            )
            env_quiet_start = parse_time_or_none(settings.QUIET_HOURS_START)
            env_quiet_end = parse_time_or_none(settings.QUIET_HOURS_END)
            if env_quiet_start is not None or env_quiet_end is not None:
                quiet_start, quiet_end = env_quiet_start, env_quiet_end
            else:
                quiet_start, quiet_end = yaml_quiet_start, yaml_quiet_end
            if events:
                self.scheduler = ProactiveScheduler(
                    events=events,
                    on_fire=self._on_scheduled_event,
                    quiet_start=quiet_start,
                    quiet_end=quiet_end,
                )
                logger.info("Loaded %d scheduled event(s) for %s",
                            len(events), self.personality.name)

        self.audio_player = AudioPlayer(on_playback_complete=self._on_playback_complete)

        # Initialize filler phrase manager with personality-specific directory, phrases, and device type
        # This pre-loads all filler audio into memory for instant access
        self.filler_manager = FillerPhraseManager(
            self.personality.filler_audio_dir,
            self.personality.filler_phrases,
            settings.OUTPUT_DEVICE_TYPE
        )
        if self.filler_manager.has_fillers:
            logger.info(f"Filler phrases ready ({len(self.filler_manager.filler_entries)} phrases catalogued)")
        else:
            logger.warning("No filler phrases found - run scripts/generate_fillers.py to create them")

        # Register state callbacks
        self._register_state_callbacks()

        # Running flag
        self._running = False
        # Set to True at the start of stop() so any in-flight scheduler
        # callback can short-circuit before re-initializing audio resources
        # the rest of the app has already torn down.
        self._shutting_down = False
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

        # Start the proactive scheduler (no-op if no events configured)
        if self.scheduler:
            self.scheduler.start()

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
        # Set BEFORE stopping the scheduler so an in-flight callback observes
        # it on its next blocking-call boundary and aborts cleanly instead of
        # racing audio_player.cleanup() below.
        self._shutting_down = True

        # Stop scheduler so no late ticks fire while subsystems are tearing down
        if self.scheduler:
            self.scheduler.stop()

        # Stop heartbeat so the supervisor sees us go silent if any of the
        # subsystem teardowns below hang.
        if self.heartbeat:
            self.heartbeat.stop()

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

        # Only start recording if not already running
        # (When continuing conversation, recorder is already in continuous mode)
        if not self.audio_recorder.is_recording:
            # New conversation from IDLE - start continuous recording session
            post_wake_audio = self.wake_word_detector.get_post_wake_audio()
            logger.info("Starting new continuous conversation recording session")
            self.audio_recorder.start_recording(initial_audio=post_wake_audio, continuous=True)
        else:
            logger.info("Continuing conversation - recorder already running in continuous mode")
            # Recorder was paused for playback; resume so the user's follow-up
            # gets captured. Wake-word stays paused for the rest of the session.
            self.audio_recorder.resume()

    def _on_enter_processing(self):
        """Handle entering PROCESSING state."""
        logger.info("Entering PROCESSING state - transcribing and generating response...")

        # Filler will be added to playback queue in _process_and_speak
        # (no longer playing it separately to avoid race conditions)

        # Processing will be handled by _on_speech_end callback

    def _on_enter_speaking(self):
        """Handle entering SPEAKING state."""
        logger.info("Entering SPEAKING state - playing response...")

        # Mute the recorder so the bot's playback doesn't end up in the next
        # captured buffer. Idempotent if already paused for a preceding filler.
        self.audio_recorder.pause()

        # Speaking will be handled by _process_and_speak method

    def _on_enter_idle(self):
        """Handle entering IDLE state."""
        logger.info("Entering IDLE state - waiting for wake word...")

        # Resume wake word detector FIRST (before stopping recorder which can block)
        self._resume_wake_after_playback()

        # Stop any ongoing recording (end continuous conversation mode)
        if self.audio_recorder.is_recording:
            logger.info("Stopping continuous recording session")
            self.audio_recorder.stop_recording()

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

        # Multi-stage audio validation (filters silence before Whisper API call)
        # Stage 1: RMS check - filters pure silence and very quiet audio
        # Use peak RMS over 100ms windows to detect ANY speech in the buffer
        peak_rms = calculate_rms(audio_data, sample_rate=16000)  # Whisper uses 16kHz

        # Log RMS value for threshold tuning
        logger.info(f"📊 Audio Peak RMS: {peak_rms:.1f} (threshold: {settings.MIN_AUDIO_RMS})")

        if peak_rms < settings.MIN_AUDIO_RMS:
            logger.info(f"Audio too quiet (Peak RMS {peak_rms:.0f} < {settings.MIN_AUDIO_RMS}), likely silence - returning to IDLE")
            self.state_machine.transition_to(ConversationState.IDLE, trigger="silence_timeout")
            return

        # Stage 2: VAD-based speech detection - filters noise/background that passes RMS
        # This catches cases where audio has sufficient volume but no actual speech
        # (e.g., background noise, music, rustling) that would cause Whisper hallucinations
        if not contains_speech(audio_data, sample_rate=16000,
                              vad_aggressiveness=settings.VAD_AGGRESSIVENESS,
                              min_speech_ratio=settings.MIN_SPEECH_RATIO):
            logger.info(f"No meaningful speech detected in audio - likely background noise - returning to IDLE")
            self.state_machine.transition_to(ConversationState.IDLE, trigger="no_speech_detected")
            return

        logger.info(f"Audio passed validation (Peak RMS: {peak_rms:.0f}, speech detected), proceeding to transcription")

        # Save debug audio if enabled (async - non-blocking)
        if settings.SAVE_DEBUG_AUDIO:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = settings.DEBUG_AUDIO_PATH / f"input_{timestamp}.wav"
            save_async(save_audio_to_wav, audio_data, str(filename))

        # Select filler FIRST (before state transition) so we can pass its context to the LLM
        filler_context = None
        if settings.ENABLE_FILLER_AUDIO and self.filler_manager.has_fillers:
            filler_result = self.filler_manager.get_random_filler()
            if filler_result:
                self._selected_filler = filler_result  # Store for later playback
                filler_context = filler_result[2]  # Extract text
                logger.info(f"Selected filler context for LLM: {filler_context[:50]}...")
        elif not settings.ENABLE_FILLER_AUDIO:
            logger.debug("Filler audio disabled by ENABLE_FILLER_AUDIO setting")

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
            # Start the playback worker and enqueue the filler before calling
            # Whisper so the filler plays in parallel with transcription.
            playback_queue = queue.Queue()
            playback_done = threading.Event()
            playback_error = None

            def playback_worker():
                """Background thread that plays chunks sequentially from the queue."""
                nonlocal playback_error
                session_started = False
                try:
                    chunk_count = 0
                    is_first_real_chunk = True  # Track first non-filler chunk
                    is_first_item = True  # Track first item (filler or chunk)

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

                        # Start playback session on FIRST item (filler or chunk) for gapless playback
                        if is_first_item:
                            # Use the sample rate from the first item (device-dependent: 48kHz for Squawkers, 44.1kHz for Teddy)
                            logger.info(f"Starting playback session for gapless playback at {sample_rate}Hz")
                            if not self.audio_player.start_playback_session(sample_rate=sample_rate):
                                logger.error("Failed to start playback session, falling back to single-shot playback")
                            else:
                                session_started = True
                            is_first_item = False

                        # Transition to SPEAKING state before first real chunk (after filler)
                        if chunk_type == "chunk" and is_first_real_chunk:
                            logger.info(f"First response chunk ready, transitioning to SPEAKING state")
                            self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_ready")
                            is_first_real_chunk = False

                        # Play this item using session (gapless for both filler and chunks)
                        logger.info(f"{chunk_type.capitalize()} {chunk_id}: Playing NOW...")

                        if session_started:
                            # Use session playback for gapless audio (both filler and chunks)
                            logger.debug(f"{chunk_type.capitalize()} {chunk_id}: Writing to session stream")
                            success = self.audio_player.write_session_chunk(stereo_audio, sample_rate)

                            if not success:
                                logger.warning(f"{chunk_type.capitalize()} {chunk_id}: Session write failed - DROPPING")
                            else:
                                logger.info(f"{chunk_type.capitalize()} {chunk_id}: Written to session successfully")
                        else:
                            # Fallback to single-shot if session failed to start
                            logger.debug(f"{chunk_type.capitalize()} {chunk_id}: Using fallback play_stereo (session not started)")
                            # Use preroll only for filler when in fallback mode
                            preroll = None if chunk_type == "filler" else 0
                            success = self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=True, preroll_ms=preroll)

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
                    # End playback session if it was started
                    if session_started:
                        logger.info("Ending playback session")
                        self.audio_player.end_playback_session()
                    playback_done.set()

            # Mark sequential playback as active (disables premature IDLE transitions)
            self._sequential_playback_active = True

            # Start playback worker thread
            playback_thread = threading.Thread(target=playback_worker, daemon=True)
            playback_thread.start()

            # Enqueue the filler before Whisper. _on_speech_end's validation
            # already gave us high confidence in the audio; the post-Whisper
            # transcript checks (hallucination / empty / meaningless) are rare
            # fallbacks that we accept may leave the filler playing through to
            # its natural end.
            if self._selected_filler:
                stereo_audio, sample_rate, _ = self._selected_filler
                logger.info("Adding filler to playback queue (will play in parallel with Whisper)")
                playback_queue.put((stereo_audio, sample_rate, "filler", "filler"))
                self._pause_wake_for_playback()
                self.audio_recorder.pause()

            def _abort_playback():
                # Sentinel is appended behind any in-flight filler, so this
                # blocks until the filler finishes naturally (up to ~15 s).
                # That's preferable to chopping mid-phrase.
                playback_queue.put(None)
                playback_thread.join(timeout=15)
                self._sequential_playback_active = False

            def _abort_to_idle(trigger: str):
                _abort_playback()
                self.state_machine.transition_to(ConversationState.IDLE, trigger=trigger)

            # Step 1: Transcribe audio (filler is already playing in parallel)
            logger.info("Step 1: Transcribing speech...")
            transcript = self.speech_to_text.transcribe_with_retry(audio_data)

            if not transcript:
                logger.warning("Transcription failed or empty")
                _abort_to_idle("transcription_failed")
                return

            transcript_clean = transcript.strip()
            transcript_words = transcript_clean.strip('.,!?;:-').strip()

            if transcript_words.lower() in WHISPER_SILENCE_HALLUCINATIONS:
                logger.info(f"Detected Whisper silence hallucination: \"{transcript}\" - returning to IDLE")
                _abort_to_idle("silence_hallucination")
                return

            meaningless_words = {'um', 'uh', 'er', 'ah', 'hmm', 'mhmm', 'mm'}
            if (len(transcript_words) < 2 or
                transcript_words.lower() in meaningless_words or
                not any(c.isalnum() for c in transcript_words)):
                logger.info(f"Transcript too short or meaningless: \"{transcript}\" - returning to IDLE")
                _abort_to_idle("empty_speech")
                return

            logger.info(f"Transcript: \"{transcript}\"")
            logger.info("Step 2: Streaming response with sentence-by-sentence pipeline...")

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

            full_response_text = ""
            chunk_num = 0
            first_chunk = True
            chunks_attempted = 0
            debug_chunks = []

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
                _abort_to_idle("generation_failed")
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

    def _on_scheduled_event(self, event: ScheduledEvent) -> None:
        """Run a scheduled event. Suppressed if a conversation is already in progress.

        Uses a non-streaming path: scheduled events are typically short utterances
        ("Good morning!", "Bedtime story time."), so the chunked-streaming pipeline
        adds complexity without latency benefit.

        Each blocking call (LLM, TTS, device) is followed by a `_shutting_down`
        check so a callback that's already in flight when stop() is called
        bails out before touching audio resources the rest of the app has
        already cleaned up.
        """
        if self._shutting_down:
            return
        if self.state_machine.state != ConversationState.IDLE:
            logger.info(
                "Scheduled event %r skipped (state=%s, would interrupt)",
                event.name, self.state_machine.state,
            )
            return

        # Resolve text to speak
        if event.say:
            text_to_speak = event.say
        else:
            logger.info("Scheduled event %r: asking LLM for response to %r", event.name, event.prompt)
            text_to_speak = self.conversation_engine.generate_response_with_retry(event.prompt)
            if not text_to_speak:
                logger.warning("Scheduled event %r: LLM returned empty response", event.name)
                return
        if self._shutting_down:
            return

        logger.info("Scheduled event %r speaking: %s", event.name, text_to_speak)

        # Synthesize and play through the device pipeline
        voice_audio_mp3 = self.text_to_speech.synthesize_with_retry(text_to_speak)
        if not voice_audio_mp3:
            logger.warning("Scheduled event %r: TTS failed", event.name)
            return
        if self._shutting_down:
            return

        result = self.output_device.create_output(voice_audio_mp3, text_to_speak, self.personality)
        if not result:
            logger.warning("Scheduled event %r: device output failed", event.name)
            return
        if self._shutting_down:
            return

        stereo_audio, sample_rate = result

        # Atomic IDLE → SPEAKING transition closes the TOCTOU window with
        # the wake-word detector that runs on its own thread.
        if not self.state_machine.try_transition(
            ConversationState.IDLE, ConversationState.SPEAKING, trigger="scheduled_event"
        ):
            logger.info(
                "Scheduled event %r could not enter SPEAKING (state=%s)",
                event.name, self.state_machine.state,
            )
            return

        # Now that we hold SPEAKING, pause wake detection.
        self._pause_wake_for_playback()

        # Non-blocking play; _on_playback_complete returns us to IDLE.
        # If the player is busy (returns False), recover the state machine
        # so we don't leak a stuck SPEAKING.
        started = self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=False)
        if not started:
            logger.warning(
                "Scheduled event %r: audio player was busy; releasing SPEAKING",
                event.name,
            )
            self._resume_wake_after_playback()
            self.state_machine.transition_to(ConversationState.IDLE, trigger="scheduled_event_failed")

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
                # Only mark as paused once pause() actually succeeded — otherwise
                # _resume_wake_after_playback would short-circuit and leave wake
                # detection silent.
                self._wake_paused_for_playback = True
            except Exception as e:
                logger.error(f"Error pausing wake word detector: {e}")

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
    # When running under the supervisor, the supervisor is the sole spawner —
    # don't let kill_existing_instances() take out the supervisor's other
    # children (e.g., a previous instance still draining shutdown).
    if not os.environ.get("HEARTBEAT_FILE"):
        kill_existing_instances()

    app: Optional[TeddyRuxpinApp] = None

    def signal_handler(sig, frame):
        logger.info("Signal %s received, shutting down...", sig)
        if app is not None:
            # Cooperative shutdown — flip the flag and let the main loop's
            # finally clause run stop(). Calling sys.exit() from a signal
            # handler bypasses cleanup and can leave the heartbeat thread
            # writing into a half-torn-down interpreter.
            app._running = False
        else:
            # SIGTERM arrived during TeddyRuxpinApp.__init__ (RVC warmup,
            # model loading, etc. can take 10s+). There's no app loop to
            # flip yet; raise SystemExit so the constructor unwinds through
            # normal exception handling. The supervisor would otherwise have
            # to escalate to SIGKILL after shutdown_grace.
            raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app = TeddyRuxpinApp()
        app.start()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
