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

from teddy_ruxpin.config import settings
from personalities import get_personality
from teddy_ruxpin.modules.state_machine import StateMachine, ConversationState
from teddy_ruxpin.modules.wake_word import WakeWordDetector
from teddy_ruxpin.modules.audio_input import AudioRecorder, save_audio_to_wav
from teddy_ruxpin.modules.speech_to_text import SpeechToText
from teddy_ruxpin.modules.conversation import ConversationEngine
from teddy_ruxpin.modules.text_to_speech import TextToSpeech
from teddy_ruxpin.modules.animatronic_control import AnimatronicControlGenerator, save_stereo_wav
from teddy_ruxpin.modules.audio_output import AudioPlayer
from teddy_ruxpin.modules.filler_phrases import FillerPhraseManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('teddy_ruxpin.log')
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
        self.control_generator = AnimatronicControlGenerator()
        self.audio_player = AudioPlayer(on_playback_complete=self._on_playback_complete)

        # Initialize filler phrase manager with personality-specific directory and phrases
        self.filler_manager = FillerPhraseManager(
            self.personality.filler_audio_dir,
            self.personality.filler_phrases
        )
        if self.filler_manager.has_fillers:
            logger.info(f"Filler phrases enabled ({len(self.filler_manager.filler_files)} phrases)")
        else:
            logger.warning("No filler phrases found - run scripts/generate_fillers.py to create them")

        # Register state callbacks
        self._register_state_callbacks()

        # Running flag
        self._running = False
        self._filler_playing = False
        self._selected_filler = None  # Store pre-selected filler for playback
        self._wake_paused_for_playback = False

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
            while self._running:
                time.sleep(0.1)

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

        logger.info("Application stopped")

    # -------------------------------------------------------------------------
    # Wake Word Detection
    # -------------------------------------------------------------------------

    def _on_wake_word(self):
        """Handle wake word detection."""
        logger.info("Wake word detected!")

        # Transition to LISTENING state
        self.state_machine.transition_to(ConversationState.LISTENING, trigger="wake_word")

    # -------------------------------------------------------------------------
    # State Callbacks
    # -------------------------------------------------------------------------

    def _on_enter_listening(self):
        """Handle entering LISTENING state."""
        logger.info("Entering LISTENING state - recording audio...")

        # Pause wake word detector while listening to user
        self.wake_word_detector.pause()

        # Start recording
        self.audio_recorder.start_recording()

    def _on_enter_processing(self):
        """Handle entering PROCESSING state."""
        logger.info("Entering PROCESSING state - transcribing and generating response...")

        # Play filler immediately for low-latency response
        if self.filler_manager.has_fillers:
            self._play_filler()

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

        # Save debug audio if enabled
        if settings.SAVE_DEBUG_AUDIO:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = settings.DEBUG_AUDIO_PATH / f"input_{timestamp}.wav"
            save_audio_to_wav(audio_data, str(filename))

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
        Process audio and generate response.

        Args:
            audio_data: Recorded audio data
            filler_context: Text of the filler phrase being played (for seamless transition)
        """
        try:
            # Step 1: Transcribe audio
            logger.info("Step 1/4: Transcribing speech...")
            transcript = self.speech_to_text.transcribe_with_retry(audio_data)

            if not transcript:
                logger.warning("Transcription failed or empty")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="transcription_failed")
                return

            logger.info(f"Transcript: \"{transcript}\"")

            # Step 2: Generate GPT response with filler context for seamless transition
            logger.info("Step 2/4: Generating response...")
            if filler_context:
                # Add filler context as a system message for smooth transition
                context_prompt = f"""[IMPORTANT CONTEXT: You just said this to the customer while thinking: "{filler_context}"]

Your response must create a seamless, natural continuation. Follow these guidelines:
1. Pick up grammatically and syntactically where the filler left off
2. If the filler ended with "Now..." or "So..." or "Alright..." - continue directly without repeating these words
3. Match the tone and energy of how you ended the filler phrase
4. Don't acknowledge or reference that you were doing something else - stay in character
5. Make it sound like one continuous thought, not two separate statements

Now respond to their question naturally, as if your filler phrase was the beginning of this same thought."""
                response_text = self.conversation_engine.generate_response_with_retry(
                    transcript,
                    additional_context=context_prompt
                )
            else:
                response_text = self.conversation_engine.generate_response_with_retry(transcript)

            if not response_text:
                logger.warning("Response generation failed")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="response_failed")
                return

            logger.info(f"Response: \"{response_text}\"")

            # Step 3: Synthesize speech
            logger.info("Step 3/4: Synthesizing speech...")
            voice_audio_mp3 = self.text_to_speech.synthesize_with_retry(response_text)

            if not voice_audio_mp3:
                logger.warning("Speech synthesis failed")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="synthesis_failed")
                return

            # Step 4: Generate control signals and create stereo output
            logger.info("Step 4/4: Generating animatronic control signals...")
            result = self.control_generator.create_stereo_output(voice_audio_mp3, response_text)

            if not result:
                logger.warning("Control signal generation failed")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="control_failed")
                return

            stereo_audio, sample_rate = result

            # Save debug audio if enabled
            if settings.SAVE_DEBUG_AUDIO:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = settings.DEBUG_AUDIO_PATH / f"output_{timestamp}.wav"
                save_stereo_wav(stereo_audio, sample_rate, str(filename))

            # Wait for filler to finish if still playing
            if self._filler_playing:
                logger.info("Waiting for filler to complete...")
                while self._filler_playing and self.audio_player.is_playing:
                    time.sleep(0.05)  # Poll every 50ms
                # No pause - immediate seamless transition to real response

            # Transition to SPEAKING state
            self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_ready")

            # Play stereo audio
            logger.info("Playing response audio...")
            self._pause_wake_for_playback()
            self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=True)

        except Exception as e:
            logger.error(f"Error in processing pipeline: {e}", exc_info=True)
            self.state_machine.transition_to(ConversationState.IDLE, trigger="error")

    def _play_filler(self):
        """Play the pre-selected filler phrase for low-latency response."""
        try:
            # Use pre-selected filler (already chosen in _on_speech_end)
            if not self._selected_filler:
                logger.warning("No filler selected")
                return

            stereo_audio, sample_rate, _ = self._selected_filler  # Unpack (ignore text here)

            # Wait 0.5 seconds before playing filler (gives natural pause + extra processing time)
            logger.debug("Pausing 0.5 seconds before filler...")
            time.sleep(0.5)

            logger.info("Playing filler phrase (non-blocking)...")
            self._filler_playing = True
            self._pause_wake_for_playback()
            # Play in non-blocking mode so processing can continue
            self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=False)

        except Exception as e:
            logger.error(f"Error playing filler: {e}", exc_info=True)
            self._filler_playing = False

    def _on_playback_complete(self):
        """Handle playback completion."""
        logger.info("Playback complete")

        # Clear filler flag if it was playing
        if self._filler_playing:
            logger.debug("Filler playback complete")
            self._filler_playing = False
            # Don't transition to IDLE yet - real response may be coming
            return

        # Resume wake word detector after all playback finishes
        self._resume_wake_after_playback()

        # Return to IDLE state (after real response)
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

            # Check if this is a python process running teddy_ruxpin.main
            cmdline = process.cmdline()
            if cmdline and 'python' in cmdline[0].lower():
                cmdline_str = ' '.join(cmdline)
                if 'teddy_ruxpin.main' in cmdline_str or 'teddy_ruxpin/main.py' in cmdline_str:
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
