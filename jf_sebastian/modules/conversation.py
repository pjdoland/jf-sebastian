"""
Conversation engine for managing GPT-4o interactions.
Maintains conversation history and generates responses.
"""

import json
import logging
import time
from typing import Optional, Generator, Tuple
from collections import deque

from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from jf_sebastian.config import settings
from jf_sebastian.utils.context_provider import get_realworld_context
from jf_sebastian.modules.spotify_tool import OPENAI_TOOLS
from jf_sebastian.modules.sentence_chunker import SentenceChunker

logger = logging.getLogger(__name__)


class ConversationEngine:
    """
    Manages conversation with GPT-4o, including context and history.
    """

    def __init__(self, system_prompt: str, spotify_tool=None, spotify_enabled: bool = False):
        """
        Initialize conversation engine.

        Args:
            system_prompt: Personality-specific system prompt for the LLM
            spotify_tool: Optional SpotifyTool for playback control (function calling)
            spotify_enabled: Whether this personality may use the Spotify tools
        """
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in configuration")

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.system_prompt = system_prompt

        # Optional playback tools. Active only when a tool is supplied AND the
        # personality opted in. When a play/resume/transfer fires, suppress_followup
        # tells the app to go IDLE (not re-open the mic over a music bed).
        self._spotify_tool = spotify_tool
        self._spotify_enabled = bool(spotify_enabled and spotify_tool is not None)
        self.suppress_followup = False

        # Conversation history holds ONLY the user/assistant turns. The system
        # prompt is pinned separately and prepended at request time, so it is
        # never evicted by the deque's maxlen as the conversation grows (which
        # would make the personality drift out of character after ~MAX_HISTORY
        # messages). MAX_HISTORY_LENGTH now bounds turns only.
        self._messages = deque(maxlen=settings.MAX_HISTORY_LENGTH)

        self._last_interaction_time = time.time()

        logger.info(f"Conversation engine initialized (model={settings.GPT_MODEL})")

    # ----- playback tools -------------------------------------------------

    def _execute_tools(self, tool_calls: dict) -> str:
        """Run the accumulated tool calls and return a short spoken confirmation.
        The SpotifyTool never raises (every failure is a neutral spoken hint), so
        a flaky API can't break the turn. A tool declares via its result whether
        it started music (suppress_followup) -- the engine stays tool-agnostic."""
        parts = []
        for slot in tool_calls.values():
            name = slot.get("name")
            if not name:
                continue
            raw = slot.get("args", "") or ""
            try:
                args = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                logger.warning("Tool %s: unparseable arguments, using empty args", name)
                args = {}
            result = self._spotify_tool.dispatch(name, args)
            parts.append(result.spoken_hint)
            if result.ok and result.suppress_followup:
                self.suppress_followup = True  # music is playing -> go IDLE, don't listen over it
        return " ".join(p for p in parts if p).strip()

    def _is_gpt5_or_newer(self) -> bool:
        """
        Determine if the model is GPT-5 or newer.

        GPT-5+ models have different API parameter requirements than GPT-4 and older.

        Returns:
            True if GPT-5 or newer, False otherwise
        """
        model = settings.GPT_MODEL.lower()
        return 'gpt-5' in model

    def _uses_max_completion_tokens(self) -> bool:
        """
        Determine if the model uses max_completion_tokens instead of max_tokens.

        Returns:
            True if model uses max_completion_tokens, False if it uses max_tokens
        """
        return self._is_gpt5_or_newer()

    def _supports_custom_temperature(self) -> bool:
        """
        Determine if the model supports custom temperature values.

        GPT-5+ only supports the default temperature of 1.0.

        Returns:
            True if model supports custom temperature, False otherwise
        """
        return not self._is_gpt5_or_newer()

    def _reasoning_effort(self) -> Optional[str]:
        """
        reasoning_effort to send for GPT-5-family models.

        Returns the configured GPT_REASONING_EFFORT (e.g. 'low'/'medium'/'high')
        for GPT-5+ models, or None to omit the parameter and use the model
        default. Always None for GPT-4 models, which have no reasoning parameter.
        """
        if not self._is_gpt5_or_newer():
            return None
        effort = (settings.GPT_REASONING_EFFORT or "").strip()
        return effort or None

    def _build_turn_context(self) -> str:
        """Transient per-turn system context: real-world info (date/weather/news)
        plus, when Spotify is enabled, the currently-playing track so the
        personality can answer questions about it. The now-playing lookup is
        cached and non-blocking."""
        parts = [get_realworld_context()]
        if self._spotify_enabled and settings.SPOTIFY_NOW_PLAYING_CONTEXT:
            now_playing = self._spotify_tool.now_playing_context()
            if now_playing:
                parts.append(now_playing)
        return "\n".join(p for p in parts if p)

    def _get_effective_max_tokens(self, requested_tokens: int) -> int:
        """
        Get the effective max tokens value for the current model.

        GPT-5+ requires higher max_completion_tokens values than GPT-4's max_tokens.
        Testing shows GPT-5 models need at least 3500 tokens when using system prompts
        and context, while GPT-4 works fine with 200-300. This is only a ceiling;
        short conversational replies consume far fewer tokens.

        Args:
            requested_tokens: The configured token limit

        Returns:
            Adjusted token limit appropriate for the model
        """
        if self._is_gpt5_or_newer():
            # GPT-5+ requires much higher token limits (minimum ~3500)
            # Scale up requested tokens significantly, with a minimum of 3500
            adjusted = max(requested_tokens * 18, 3500)
            if adjusted != requested_tokens:
                logger.debug(f"Adjusted token limit for GPT-5+: {requested_tokens} -> {adjusted}")
            return adjusted
        else:
            # GPT-4 and older work fine with configured values
            return requested_tokens

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

            # Pinned system prompt + turns, then insert the transient real-world
            # context just before the latest user turn (none of these are stored
            # back into the turn history)
            messages = self._messages_with_system()
            messages.insert(-1, {"role": "system", "content": self._build_turn_context()})

            # Call GPT API with appropriate parameters
            api_params = {
                "model": settings.GPT_MODEL,
                "messages": messages,
            }

            # Add temperature if supported (GPT-4 and older)
            if self._supports_custom_temperature():
                api_params["temperature"] = 0.8  # Slightly creative for personality

            # Add token limit parameter (name varies by model version)
            effective_tokens = self._get_effective_max_tokens(settings.MAX_TOKENS)
            if self._uses_max_completion_tokens():
                api_params["max_completion_tokens"] = effective_tokens
            else:
                api_params["max_tokens"] = effective_tokens

            # Add reasoning effort for the GPT-5 family (omitted for GPT-4)
            effort = self._reasoning_effort()
            if effort:
                api_params["reasoning_effort"] = effort

            response = self.client.chat.completions.create(**api_params)

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

    def generate_response_streaming(self, user_input: str, additional_context: Optional[str] = None) -> Generator[Tuple[str, bool], None, None]:
        """
        Generate response with streaming - yields chunks based on word count threshold.

        This enables starting TTS/RVC while the LLM is still generating the rest.
        Each chunk contains the minimum number of complete sentences that exceeds
        the MIN_CHUNK_WORDS threshold (configurable in .env), except the last chunk
        which contains the remainder regardless of word count.

        Args:
            user_input: User's message text
            additional_context: Optional context to prepend (e.g., filler phrase)

        Yields:
            Tuples of (text_chunk, is_final):
            - First yield: (first_chunk, False) - minimum sentences exceeding word threshold
            - Subsequent yields: (remaining_chunks, False) - each exceeding word threshold
            - Last text chunk: (remainder, False) - final sentences regardless of length
            - Final yield: ("", True) when complete

        Example:
            for chunk, is_final in engine.generate_response_streaming("Hello"):
                if not is_final:
                    process_chunk(chunk)  # Start TTS on chunk
                else:
                    finish_up()  # LLM is done
        """
        if not user_input or not user_input.strip():
            logger.warning("Empty user input provided")
            return

        # Check conversation timeout
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

            logger.info(f"Generating streaming response to: \"{user_input}\"")

            # Pinned system prompt + turns, then insert the transient real-world
            # context just before the latest user turn (none of these are stored
            # back into the turn history)
            messages = self._messages_with_system()
            messages.insert(-1, {"role": "system", "content": self._build_turn_context()})

            # Call GPT API with streaming and appropriate parameters
            api_params = {
                "model": settings.GPT_MODEL,
                "messages": messages,
                "stream": True  # Enable streaming!
            }

            # Add temperature if supported (GPT-4 and older)
            if self._supports_custom_temperature():
                api_params["temperature"] = 0.8

            # Add token limit parameter (name varies by model version)
            effective_tokens = self._get_effective_max_tokens(settings.MAX_TOKENS_STREAMING)
            if self._uses_max_completion_tokens():
                api_params["max_completion_tokens"] = effective_tokens
            else:
                api_params["max_tokens"] = effective_tokens

            # Offer playback tools only when the personality opted in. On a normal
            # turn the model streams content and this is a no-op; on an action turn
            # it streams tool_calls instead (handled after the loop).
            self.suppress_followup = False
            if self._spotify_enabled:
                api_params["tools"] = OPENAI_TOOLS
                api_params["tool_choice"] = "auto"
                # NOTE: gpt-5.x rejects reasoning_effort combined with function
                # tools on /v1/chat/completions (400), so it is intentionally
                # omitted on tool-enabled turns; the model's default reasoning
                # applies instead.
            else:
                # Reasoning effort for the GPT-5 family (omitted for GPT-4)
                effort = self._reasoning_effort()
                if effort:
                    api_params["reasoning_effort"] = effort

            stream = self.client.chat.completions.create(**api_params)

            # Accumulate the full response and feed the streaming chunker, which
            # yields speakable chunks (>= MIN_CHUNK_WORDS, abbreviation-aware, with
            # a soft cap for run-ons) as they complete.
            full_response = ""
            chunk_count = 0
            chunker = SentenceChunker(settings.MIN_CHUNK_WORDS)

            # Accumulate any tool-call deltas (id/name arrive on the first fragment,
            # arguments stream as a split string) keyed by index; act after the loop.
            tool_calls = {}
            tools_on = self._spotify_enabled  # short-circuits the per-token check below

            for chunk in stream:
                delta = chunk.choices[0].delta
                if tools_on and getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        slot = tool_calls.setdefault(tc.index, {"name": None, "args": ""})
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            slot["args"] += tc.function.arguments
                if delta.content:
                    full_response += delta.content
                    for piece in chunker.feed(delta.content):
                        chunk_count += 1
                        logger.info(f"Chunk {chunk_count} ready ({len(piece.split())} words): \"{piece[:80]}...\"")
                        yield (piece, False)

            # Flush any remaining text as the final chunk (regardless of word count)
            tail = chunker.flush()
            if tail:
                chunk_count += 1
                logger.info(f"Final chunk {chunk_count} ({len(tail.split())} words): \"{tail[:80]}...\"")
                yield (tail, False)

            # If the model called playback tools, execute them and speak a
            # templated confirmation in the personality's voice (no 2nd LLM call).
            # Tool scaffolding is NOT persisted to history -- that avoids the strict
            # assistant-with-tool_calls -> tool-role message sequence and its
            # deque-eviction corruption; we store only a clean spoken summary.
            if tool_calls and self._spotify_enabled:
                confirmation = self._execute_tools(tool_calls)
                # Keep BOTH any spoken preamble (already yielded during the loop)
                # and the confirmation in history, so neither is lost from context
                # if the model both talked and called a tool.
                spoken = " ".join(p for p in (full_response.strip(), confirmation) if p).strip()
                self._messages.append({"role": "assistant", "content": spoken})
                if confirmation:
                    yield (confirmation, False)
                self._last_interaction_time = time.time()
                logger.info("Streaming complete (tool turn).")
                yield ("", True)
                return

            # Add complete response to history
            self._messages.append({
                "role": "assistant",
                "content": full_response.strip()
            })

            self._last_interaction_time = time.time()
            logger.info(f"Streaming complete. Full response: \"{full_response.strip()}\"")

            # Signal completion
            yield ("", True)

        except Exception as e:
            logger.error(f"Error in streaming response: {e}", exc_info=True)

            # Clean up partial user message if present
            if len(self._messages) > 0 and self._messages[-1]["role"] == "user":
                logger.warning("Removing partial user message due to streaming error")
                self._messages.pop()

            # Update interaction time even on error
            self._last_interaction_time = time.time()

            # Yield error response
            error_msg = self._get_error_response("unknown")
            yield (error_msg, False)
            yield ("", True)

    def clear_history(self):
        """Clear the conversation turns. The system prompt is pinned separately,
        so it survives the clear."""
        self._messages.clear()
        logger.info("Conversation history cleared")

    def _messages_with_system(self) -> list[dict]:
        """A fresh list of the pinned system prompt followed by the bounded turn
        history. The system prompt lives outside the maxlen deque, so it is never
        evicted as turns accumulate. Returns a new list each call, safe to mutate."""
        return [{"role": "system", "content": self.system_prompt}, *self._messages]

    def get_history(self) -> list[dict]:
        """Get the full conversation as sent to the model: the pinned system
        prompt followed by the user/assistant turns."""
        return self._messages_with_system()

    def get_history_length(self) -> int:
        """Get number of messages in history (the pinned system prompt + turns)."""
        return len(self._messages_with_system())

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
