"""
Text-to-speech module using OpenAI TTS API.
Converts text responses to audio for Teddy Ruxpin.
"""

import logging
import io
from typing import Optional

from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from teddy_ruxpin.config import settings

logger = logging.getLogger(__name__)


class TextToSpeech:
    """
    Handles text-to-speech synthesis using OpenAI TTS API.
    """

    def __init__(self, voice: str = "onyx", speed: float = 1.0, style_instruction: Optional[str] = None):
        """
        Initialize TTS client.

        Args:
            voice: OpenAI TTS voice ID (e.g., 'onyx', 'echo', 'fable')
            speed: Default speech speed (0.25 to 4.0)
            style_instruction: Optional style instruction for gpt-4o-mini-tts model
                             (e.g., 'Speak warmly and casually', 'Use a dignified tone')
        """
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in configuration")

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.voice = voice
        self.default_speed = speed
        self.style_instruction = style_instruction
        logger.info(
            f"Text-to-speech initialized (model={settings.TTS_MODEL}, "
            f"voice={self.voice}, speed={self.default_speed}, "
            f"style={'Yes' if self.style_instruction else 'No'})"
        )

    def synthesize(self, text: str, speed: Optional[float] = None) -> Optional[bytes]:
        """
        Synthesize text to speech audio.

        Args:
            text: Text to synthesize
            speed: Speech speed (0.25 to 4.0, uses default if None)

        Returns:
            Audio data bytes (MP3 format), or None if synthesis failed
        """
        if not text or not text.strip():
            logger.warning("No text provided for synthesis")
            return None

        # Use default speed if not specified
        if speed is None:
            speed = self.default_speed

        try:
            logger.info(f"Synthesizing speech: \"{text[:80]}...\" (speed={speed})")

            # Build API parameters
            api_params = {
                "model": settings.TTS_MODEL,
                "voice": self.voice,
                "input": text,
                "speed": speed,
                "response_format": "mp3"
            }

            # Add instructions parameter for gpt-4o-mini-tts model
            if self.style_instruction and 'gpt-4o' in settings.TTS_MODEL:
                api_params["instructions"] = self.style_instruction
                logger.debug(f"Using style instructions: {self.style_instruction[:50]}...")

            # Call TTS API
            response = self.client.audio.speech.create(**api_params)

            # Get audio bytes
            audio_data = response.content

            logger.info(f"Speech synthesized successfully ({len(audio_data)} bytes)")
            return audio_data

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
            logger.error(f"Unexpected error during synthesis: {e}", exc_info=True)
            return None

    def synthesize_with_retry(
        self,
        text: str,
        speed: Optional[float] = None,
        max_retries: int = 3
    ) -> Optional[bytes]:
        """
        Synthesize with automatic retry on failure.

        Args:
            text: Text to synthesize
            speed: Speech speed (uses default if None)
            max_retries: Maximum number of retry attempts

        Returns:
            Audio data bytes, or None if all attempts failed
        """
        for attempt in range(max_retries):
            result = self.synthesize(text, speed)

            if result is not None:
                return result

            if attempt < max_retries - 1:
                logger.info(f"Synthesis attempt {attempt + 1} failed, retrying...")

        logger.error(f"Synthesis failed after {max_retries} attempts")
        return None


class MockTextToSpeech:
    """
    Mock text-to-speech for testing without API calls.
    Returns silent audio data.
    """

    def __init__(self):
        logger.info("Mock text-to-speech initialized")

    def synthesize(self, text: str, speed: float = 1.0) -> Optional[bytes]:
        """Return mock audio data (1 second of silence)."""
        if not text:
            return None

        logger.info(f"Mock synthesis: \"{text[:50]}...\"")

        # Generate 1 second of silence at 44.1kHz, 16-bit, mono
        sample_rate = settings.SAMPLE_RATE
        duration = 1.0
        num_samples = int(sample_rate * duration)

        # 16-bit silence = bytes of zeros
        silent_audio = b'\x00\x00' * num_samples

        return silent_audio

    def synthesize_with_retry(
        self,
        text: str,
        speed: float = 1.0,
        max_retries: int = 3
    ) -> Optional[bytes]:
        """Return mock audio data."""
        return self.synthesize(text, speed)
