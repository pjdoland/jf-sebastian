"""
TEST VERSION: Uses Enter key instead of wake word for easier testing.
Main application for Teddy Ruxpin AI Conversation System.
"""

import logging
import sys
import time
import signal
from pathlib import Path

from teddy_ruxpin.config import settings
from teddy_ruxpin.modules.state_machine import StateMachine, ConversationState
from teddy_ruxpin.modules.wake_word import MockWakeWordDetector  # Use mock detector
from teddy_ruxpin.modules.audio_input import AudioRecorder, save_audio_to_wav
from teddy_ruxpin.modules.speech_to_text import SpeechToText
from teddy_ruxpin.modules.conversation import ConversationEngine
from teddy_ruxpin.modules.text_to_speech import TextToSpeech
from teddy_ruxpin.modules.animatronic_control import AnimatronicControlGenerator, save_stereo_wav
from teddy_ruxpin.modules.audio_output import AudioPlayer

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('teddy_ruxpin_test.log')
    ]
)

logger = logging.getLogger(__name__)


class TeddyRuxpinApp:
    """Main application class for Teddy Ruxpin AI system (TEST MODE)."""

    def __init__(self):
        """Initialize the application."""
        logger.info("=" * 80)
        logger.info("Teddy Ruxpin AI Conversation System (TEST MODE)")
        logger.info("=" * 80)

        # Validate configuration
        errors = settings.validate()
        if errors:
            logger.error("Configuration errors:")
            for error in errors:
                # Skip Picovoice key check in test mode
                if "PICOVOICE" not in error:
                    logger.error(f"  - {error}")

        # Create debug directories if needed
        settings.create_debug_dirs()

        # Initialize state machine
        self.state_machine = StateMachine()

        # Initialize modules
        logger.info("Initializing modules...")

        self.wake_word_detector = MockWakeWordDetector(on_wake_word=self._on_wake_word)
        self.audio_recorder = AudioRecorder(on_speech_end=self._on_speech_end)
        self.speech_to_text = SpeechToText()
        self.conversation_engine = ConversationEngine()
        self.text_to_speech = TextToSpeech()
        self.control_generator = AnimatronicControlGenerator()
        self.audio_player = AudioPlayer(on_playback_complete=self._on_playback_complete)

        # Register state callbacks
        self._register_state_callbacks()

        # Running flag
        self._running = False

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

        logger.info("Starting Teddy Ruxpin AI system (TEST MODE)...")
        self._running = True

        # Start wake word detection (Enter key mode)
        self.wake_word_detector.start()

        logger.info("=" * 80)
        logger.info("System ready! Press ENTER to start talking (instead of wake word).")
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

        logger.info("Stopping Teddy Ruxpin AI system...")
        self._running = False

        # Stop modules
        self.wake_word_detector.stop()
        self.audio_player.stop()

        logger.info("Application stopped")

    def _on_wake_word(self):
        """Handle wake word detection."""
        logger.info("Wake trigger (Enter pressed)!")
        self.state_machine.transition_to(ConversationState.LISTENING, trigger="enter_key")

    def _on_enter_listening(self):
        """Handle entering LISTENING state."""
        logger.info("Entering LISTENING state - recording audio...")
        self.audio_recorder.start_recording()

    def _on_enter_processing(self):
        """Handle entering PROCESSING state."""
        logger.info("Entering PROCESSING state - transcribing and generating response...")

    def _on_enter_speaking(self):
        """Handle entering SPEAKING state."""
        logger.info("Entering SPEAKING state - playing response...")

    def _on_enter_idle(self):
        """Handle entering IDLE state."""
        logger.info("Entering IDLE state - Press ENTER for next interaction...")

        if self.conversation_engine.time_since_last_interaction > settings.CONVERSATION_TIMEOUT:
            logger.info("Clearing conversation history due to timeout")
            self.conversation_engine.clear_history()

    def _on_speech_end(self, audio_data: bytes):
        """Handle end of speech detection."""
        logger.info(f"Speech ended, captured {len(audio_data)} bytes")

        if settings.SAVE_DEBUG_AUDIO:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = settings.DEBUG_AUDIO_PATH / f"input_{timestamp}.wav"
            save_audio_to_wav(audio_data, str(filename))

        self.state_machine.transition_to(ConversationState.PROCESSING, trigger="speech_end")
        self._process_and_speak(audio_data)

    def _process_and_speak(self, audio_data: bytes):
        """Process audio and generate response."""
        try:
            # Step 1: Transcribe audio
            logger.info("Step 1/4: Transcribing speech...")
            transcript = self.speech_to_text.transcribe_with_retry(audio_data)

            if not transcript:
                logger.warning("Transcription failed or empty")
                self.state_machine.transition_to(ConversationState.IDLE, trigger="transcription_failed")
                return

            logger.info(f"Transcript: \"{transcript}\"")

            # Step 2: Generate GPT response
            logger.info("Step 2/4: Generating response...")
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

            if settings.SAVE_DEBUG_AUDIO:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = settings.DEBUG_AUDIO_PATH / f"output_{timestamp}.wav"
                save_stereo_wav(stereo_audio, sample_rate, str(filename))

            self.state_machine.transition_to(ConversationState.SPEAKING, trigger="response_ready")

            logger.info("Playing response audio...")
            self.audio_player.play_stereo(stereo_audio, sample_rate, blocking=True)

        except Exception as e:
            logger.error(f"Error in processing pipeline: {e}", exc_info=True)
            self.state_machine.transition_to(ConversationState.IDLE, trigger="error")

    def _on_playback_complete(self):
        """Handle playback completion."""
        logger.info("Playback complete")
        self.state_machine.transition_to(ConversationState.IDLE, trigger="playback_complete")


def main():
    """Main entry point."""
    def signal_handler(sig, frame):
        logger.info("Interrupt received, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        app = TeddyRuxpinApp()
        app.start()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
