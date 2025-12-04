"""
Speech-to-text transcription using OpenAI Whisper API.
Converts recorded audio to text for conversation processing.
"""

import logging
import io
from typing import Optional

from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from teddy_ruxpin.config import settings
from teddy_ruxpin.modules.audio_input import audio_data_to_wav_bytes

logger = logging.getLogger(__name__)


class SpeechToText:
    """
    Handles speech-to-text transcription using OpenAI Whisper API.
    """

    def __init__(self):
        """Initialize Whisper client."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in configuration")

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info(f"Speech-to-text initialized (model={settings.WHISPER_MODEL})")

    def transcribe(self, audio_data: bytes, language: str = "en") -> Optional[str]:
        """
        Transcribe audio data to text.

        Args:
            audio_data: Raw PCM audio data (16-bit, mono)
            language: Language code (default: "en" for English)

        Returns:
            Transcribed text, or None if transcription failed
        """
        if not audio_data or len(audio_data) == 0:
            logger.warning("No audio data provided for transcription")
            return None

        try:
            logger.info(f"Transcribing audio ({len(audio_data)} bytes)...")

            # Convert raw PCM to WAV format
            wav_data = audio_data_to_wav_bytes(audio_data, settings.SAMPLE_RATE)

            # Create file-like object for API
            audio_file = io.BytesIO(wav_data)
            audio_file.name = "audio.wav"

            # Call Whisper API
            response = self.client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=audio_file,
                language=language,
                response_format="text"
            )

            # Extract text
            text = response.strip()

            if text:
                logger.info(f"Transcription successful: \"{text}\"")
                return text
            else:
                logger.warning("Transcription returned empty text")
                return None

        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            return None

        except APIConnectionError as e:
            logger.error(f"OpenAI connection error: {e}")
            return None

        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during transcription: {e}", exc_info=True)
            return None

    def transcribe_with_retry(
        self,
        audio_data: bytes,
        language: str = "en",
        max_retries: int = 3
    ) -> Optional[str]:
        """
        Transcribe with automatic retry on failure.

        Args:
            audio_data: Raw PCM audio data
            language: Language code
            max_retries: Maximum number of retry attempts

        Returns:
            Transcribed text, or None if all attempts failed
        """
        for attempt in range(max_retries):
            result = self.transcribe(audio_data, language)

            if result is not None:
                return result

            if attempt < max_retries - 1:
                logger.info(f"Transcription attempt {attempt + 1} failed, retrying...")

        logger.error(f"Transcription failed after {max_retries} attempts")
        return None


class MockSpeechToText:
    """
    Mock speech-to-text for testing without API calls.
    Returns placeholder text.
    """

    def __init__(self):
        logger.info("Mock speech-to-text initialized")

    def transcribe(self, audio_data: bytes, language: str = "en") -> Optional[str]:
        """Return mock transcription."""
        if not audio_data:
            return None

        logger.info("Mock transcription: returning test text")
        return "This is a test transcription."

    def transcribe_with_retry(
        self,
        audio_data: bytes,
        language: str = "en",
        max_retries: int = 3
    ) -> Optional[str]:
        """Return mock transcription."""
        return self.transcribe(audio_data, language)
