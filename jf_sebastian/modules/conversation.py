"""
Conversation engine for managing GPT-4o interactions.
Maintains conversation history and generates responses.
"""

import logging
import time
from typing import Optional
from collections import deque

from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from jf_sebastian.config import settings

logger = logging.getLogger(__name__)


class ConversationEngine:
    """
    Manages conversation with GPT-4o, including context and history.
    """

    def __init__(self, system_prompt: str):
        """
        Initialize conversation engine.

        Args:
            system_prompt: Personality-specific system prompt for the LLM
        """
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in configuration")

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.system_prompt = system_prompt

        # Conversation history (system + user/assistant messages)
        self._messages = deque(maxlen=settings.MAX_HISTORY_LENGTH)

        # Add system prompt
        self._messages.append({
            "role": "system",
            "content": self.system_prompt
        })

        self._last_interaction_time = time.time()

        logger.info(f"Conversation engine initialized (model={settings.GPT_MODEL})")

    def generate_response(self, user_input: str, additional_context: Optional[str] = None) -> Optional[str]:
        """
        Generate a response to user input.

        Args:
            user_input: User's message text
            additional_context: Optional context to prepend (e.g., filler phrase for seamless transition)

        Returns:
            Assistant's response text, or None if generation failed
        """
        if not user_input or not user_input.strip():
            logger.warning("Empty user input provided")
            return None

        # Check if conversation history should be cleared (timeout)
        if time.time() - self._last_interaction_time > settings.CONVERSATION_TIMEOUT:
            logger.info("Conversation timeout reached, clearing history")
            self.clear_history()

        try:
            # Build user message with optional context
            user_message = user_input
            if additional_context:
                user_message = f"{additional_context}\n\nUser question: {user_input}"
                logger.info(f"Adding context for seamless transition: {additional_context[:50]}...")

            # Add user message to history
            self._messages.append({
                "role": "user",
                "content": user_message
            })

            logger.info(f"Generating response to: \"{user_input}\"")

            # Call GPT-4o API
            response = self.client.chat.completions.create(
                model=settings.GPT_MODEL,
                messages=list(self._messages),
                temperature=0.8,  # Slightly creative for personality
                max_tokens=150,  # Keep responses concise
            )

            # Extract assistant response
            assistant_message = response.choices[0].message.content.strip()

            # Add to history
            self._messages.append({
                "role": "assistant",
                "content": assistant_message
            })

            self._last_interaction_time = time.time()

            logger.info(f"Response generated: \"{assistant_message}\"")
            return assistant_message

        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            return self._get_error_response("rate_limit")

        except APIConnectionError as e:
            logger.error(f"OpenAI connection error: {e}")
            return self._get_error_response("connection")

        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return self._get_error_response("api")

        except Exception as e:
            logger.error(f"Unexpected error generating response: {e}", exc_info=True)
            return self._get_error_response("unknown")

    def generate_response_with_retry(self, user_input: str, max_retries: int = 3, additional_context: Optional[str] = None) -> Optional[str]:
        """
        Generate response with automatic retry on failure.

        Args:
            user_input: User's message text
            max_retries: Maximum number of retry attempts
            additional_context: Optional context to prepend (e.g., filler phrase for seamless transition)

        Returns:
            Assistant's response text, or fallback error message
        """
        for attempt in range(max_retries):
            result = self.generate_response(user_input, additional_context=additional_context)

            if result and not result.startswith("I'm having trouble"):
                return result

            if attempt < max_retries - 1:
                logger.info(f"Response generation attempt {attempt + 1} failed, retrying...")
                time.sleep(1)  # Brief delay before retry

        logger.error(f"Response generation failed after {max_retries} attempts")
        return self._get_error_response("max_retries")

    def clear_history(self):
        """Clear conversation history, keeping only system prompt."""
        self._messages.clear()
        self._messages.append({
            "role": "system",
            "content": self.system_prompt
        })
        logger.info("Conversation history cleared")

    def get_history(self) -> list[dict]:
        """Get current conversation history."""
        return list(self._messages)

    def get_history_length(self) -> int:
        """Get number of messages in history."""
        return len(self._messages)

    def _get_error_response(self, error_type: str) -> str:
        """
        Get a friendly error response based on error type.

        Args:
            error_type: Type of error (rate_limit, connection, api, unknown, max_retries)

        Returns:
            User-friendly error message in Teddy's voice
        """
        error_messages = {
            "rate_limit": "I'm having trouble thinking right now. Maybe I need a little rest?",
            "connection": "I can't seem to reach my thoughts right now. Can we try again in a moment?",
            "api": "Something's not quite right with my thinking. Let's try that again!",
            "unknown": "Oh dear, I got a bit confused. Could you say that again?",
            "max_retries": "I'm sorry, I'm having a hard time responding right now. Maybe we can try again later?",
        }

        return error_messages.get(error_type, error_messages["unknown"])

    @property
    def time_since_last_interaction(self) -> float:
        """Get seconds since last interaction."""
        return time.time() - self._last_interaction_time


class MockConversationEngine:
    """
    Mock conversation engine for testing without API calls.
    Returns pre-defined responses.
    """

    def __init__(self):
        self._interaction_count = 0
        logger.info("Mock conversation engine initialized")

    def generate_response(self, user_input: str) -> Optional[str]:
        """Return mock response."""
        if not user_input:
            return None

        self._interaction_count += 1

        responses = [
            "Hi there! I'm Teddy Ruxpin. It's wonderful to talk with you!",
            "That's really interesting! Tell me more about that.",
            "You know, in Grundo, we have something similar. It's quite magical!",
            "I love learning new things. What else would you like to talk about?",
        ]

        response = responses[self._interaction_count % len(responses)]
        logger.info(f"Mock response: \"{response}\"")
        return response

    def generate_response_with_retry(self, user_input: str, max_retries: int = 3) -> Optional[str]:
        """Return mock response."""
        return self.generate_response(user_input)

    def clear_history(self):
        """Clear mock history."""
        self._interaction_count = 0
        logger.info("Mock conversation history cleared")

    def get_history(self) -> list[dict]:
        """Return empty history."""
        return []

    def get_history_length(self) -> int:
        """Return mock history length."""
        return self._interaction_count

    @property
    def time_since_last_interaction(self) -> float:
        """Return 0 for mock."""
        return 0.0
