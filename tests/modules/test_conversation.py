"""
Tests for conversation engine module.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from collections import deque

from teddy_ruxpin.modules.conversation import ConversationEngine, MockConversationEngine
from openai import APIError, APIConnectionError, RateLimitError


# MockConversationEngine Tests

def test_mock_conversation_engine_initialization():
    """Test MockConversationEngine initialization."""
    engine = MockConversationEngine()

    assert engine._interaction_count == 0


def test_mock_conversation_engine_generate_response():
    """Test mock response generation."""
    engine = MockConversationEngine()

    response = engine.generate_response("Hello")

    assert response is not None
    assert isinstance(response, str)
    assert len(response) > 0


def test_mock_conversation_engine_empty_input():
    """Test mock engine with empty input."""
    engine = MockConversationEngine()

    response = engine.generate_response("")

    assert response is None


def test_mock_conversation_engine_cycles_responses():
    """Test that mock engine cycles through responses."""
    engine = MockConversationEngine()

    responses = []
    for i in range(8):  # More than 4 to test cycling
        response = engine.generate_response(f"Question {i}")
        responses.append(response)

    # Should cycle through 4 responses
    assert len(set(responses)) == 4
    assert responses[0] == responses[4]


def test_mock_conversation_engine_retry():
    """Test mock engine retry method."""
    engine = MockConversationEngine()

    response = engine.generate_response_with_retry("Hello", max_retries=3)

    assert response is not None
    assert isinstance(response, str)


def test_mock_conversation_engine_clear_history():
    """Test clearing mock history."""
    engine = MockConversationEngine()

    engine.generate_response("Test 1")
    engine.generate_response("Test 2")

    assert engine._interaction_count == 2

    engine.clear_history()

    assert engine._interaction_count == 0


def test_mock_conversation_engine_get_history():
    """Test getting mock history."""
    engine = MockConversationEngine()

    history = engine.get_history()

    assert isinstance(history, list)
    assert len(history) == 0


def test_mock_conversation_engine_get_history_length():
    """Test getting mock history length."""
    engine = MockConversationEngine()

    engine.generate_response("Test 1")
    engine.generate_response("Test 2")

    assert engine.get_history_length() == 2


def test_mock_conversation_engine_time_since_interaction():
    """Test time since interaction for mock."""
    engine = MockConversationEngine()

    assert engine.time_since_last_interaction == 0.0


# ConversationEngine Tests with Mocking

@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_initialization(mock_settings, mock_openai):
    """Test ConversationEngine initialization."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test system prompt")

    assert engine.system_prompt == "Test system prompt"
    assert len(engine._messages) == 1
    assert engine._messages[0]["role"] == "system"
    assert engine._messages[0]["content"] == "Test system prompt"


@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_missing_api_key(mock_settings):
    """Test initialization fails without API key."""
    mock_settings.OPENAI_API_KEY = ""

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        ConversationEngine("Test prompt")


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_generate_response_success(mock_settings, mock_openai):
    """Test successful response generation."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    # Mock OpenAI response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "This is a test response."

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Hello, how are you?")

    assert response == "This is a test response."
    assert len(engine._messages) == 3  # system + user + assistant
    mock_client.chat.completions.create.assert_called_once()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_empty_input(mock_settings, mock_openai):
    """Test response generation with empty input."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("")

    assert response is None


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_whitespace_input(mock_settings, mock_openai):
    """Test response generation with whitespace-only input."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("   ")

    assert response is None


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_with_context(mock_settings, mock_openai):
    """Test response generation with additional context."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Response with context."

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Question?", additional_context="Hmm...")

    assert response == "Response with context."
    # Check that context was added to user message
    user_message = engine._messages[1]["content"]
    assert "Hmm..." in user_message
    assert "Question?" in user_message


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_rate_limit_error(mock_settings, mock_openai):
    """Test handling of rate limit errors."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    # Create a proper mock response object for RateLimitError
    mock_response = MagicMock()
    mock_response.request = MagicMock()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RateLimitError("Rate limit", response=mock_response, body=None)
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Hello")

    assert response is not None
    assert "trouble thinking" in response.lower()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_connection_error(mock_settings, mock_openai):
    """Test handling of connection errors."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APIConnectionError(request=None)
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Hello")

    assert response is not None
    assert "reach my thoughts" in response.lower()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_api_error(mock_settings, mock_openai):
    """Test handling of generic API errors."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APIError("API Error", request=None, body=None)
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Hello")

    assert response is not None
    assert "not quite right" in response.lower()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_unknown_error(mock_settings, mock_openai):
    """Test handling of unknown errors."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Unknown error")
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response("Hello")

    assert response is not None
    assert "confused" in response.lower()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_clear_history(mock_settings, mock_openai):
    """Test clearing conversation history."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")

    # Manually add messages
    engine._messages.append({"role": "user", "content": "Test"})
    engine._messages.append({"role": "assistant", "content": "Response"})

    assert len(engine._messages) == 3

    engine.clear_history()

    # Should only have system prompt left
    assert len(engine._messages) == 1
    assert engine._messages[0]["role"] == "system"


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_get_history(mock_settings, mock_openai):
    """Test getting conversation history."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")

    engine._messages.append({"role": "user", "content": "Test"})

    history = engine.get_history()

    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0]["role"] == "system"
    assert history[1]["role"] == "user"


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_get_history_length(mock_settings, mock_openai):
    """Test getting history length."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")

    assert engine.get_history_length() == 1  # Only system prompt

    engine._messages.append({"role": "user", "content": "Test"})

    assert engine.get_history_length() == 2


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_timeout_clears_history(mock_settings, mock_openai):
    """Test that timeout clears conversation history."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 0.1  # Very short timeout

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Response"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")

    # Add a message
    engine._messages.append({"role": "user", "content": "First message"})
    assert len(engine._messages) == 2

    # Wait for timeout
    time.sleep(0.2)

    # Next response should clear history
    engine.generate_response("Second message")

    # Should have system + user + assistant (history was cleared)
    assert len(engine._messages) == 3


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_time_since_interaction(mock_settings, mock_openai):
    """Test time since last interaction."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Response"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")

    # Initial time should be very recent
    assert engine.time_since_last_interaction < 1.0

    time.sleep(0.1)

    # Generate a response
    engine.generate_response("Test")

    # Should have reset the timer
    assert engine.time_since_last_interaction < 0.1


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_generate_response_with_retry_success(mock_settings, mock_openai):
    """Test retry mechanism with eventual success."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    # Create mock responses - first returns rate limit error (triggers retry), second succeeds
    mock_response = MagicMock()
    mock_response.request = MagicMock()

    success_response = MagicMock()
    success_response.choices = [MagicMock()]
    success_response.choices[0].message.content = "Success response"

    mock_client = MagicMock()
    # First call: RateLimitError (returns "I'm having trouble..." which triggers retry)
    # Second call: Success
    mock_client.chat.completions.create.side_effect = [
        RateLimitError("Rate limit", response=mock_response, body=None),
        success_response
    ]
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response_with_retry("Test", max_retries=3)

    assert response == "Success response"


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_generate_response_with_retry_all_fail(mock_settings, mock_openai):
    """Test retry mechanism when all attempts fail."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"
    mock_settings.CONVERSATION_TIMEOUT = 300

    # Create mock response for RateLimitError
    mock_response = MagicMock()
    mock_response.request = MagicMock()

    mock_client = MagicMock()
    # All attempts return RateLimitError (which triggers retries)
    mock_client.chat.completions.create.side_effect = RateLimitError("Always fail", response=mock_response, body=None)
    mock_openai.return_value = mock_client

    engine = ConversationEngine("Test prompt")
    response = engine.generate_response_with_retry("Test", max_retries=2)

    assert response is not None
    assert "hard time responding" in response.lower()


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_max_history_length(mock_settings, mock_openai):
    """Test that history respects max length."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 5  # Small limit
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")

    # Add many messages
    for i in range(10):
        engine._messages.append({"role": "user", "content": f"Message {i}"})

    # Should be limited to max length
    assert len(engine._messages) <= 5


@patch('teddy_ruxpin.modules.conversation.OpenAI')
@patch('teddy_ruxpin.modules.conversation.settings')
def test_conversation_engine_error_response_types(mock_settings, mock_openai):
    """Test different error response types."""
    mock_settings.OPENAI_API_KEY = "test-key"
    mock_settings.MAX_HISTORY_LENGTH = 20
    mock_settings.GPT_MODEL = "gpt-4o-mini"

    engine = ConversationEngine("Test prompt")

    # Test each error type
    rate_limit_msg = engine._get_error_response("rate_limit")
    assert "trouble thinking" in rate_limit_msg.lower()

    connection_msg = engine._get_error_response("connection")
    assert "reach my thoughts" in connection_msg.lower()

    api_msg = engine._get_error_response("api")
    assert "not quite right" in api_msg.lower()

    unknown_msg = engine._get_error_response("unknown")
    assert "confused" in unknown_msg.lower()

    max_retry_msg = engine._get_error_response("max_retries")
    assert "hard time responding" in max_retry_msg.lower()

    # Unknown error type should fallback
    fallback_msg = engine._get_error_response("nonexistent_type")
    assert "confused" in fallback_msg.lower()
