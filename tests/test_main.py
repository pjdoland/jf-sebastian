"""
Tests for main application and state machine.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
from teddy_ruxpin.main import ConversationState, JFSebastian


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_jf_sebastian_initialization(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test J.F. Sebastian initialization."""
    mock_get_personality.return_value = mock_personality

    jf = JFSebastian(personality_name="johnny")

    # Should load personality
    mock_get_personality.assert_called_once_with("johnny")

    # Should initialize all modules
    mock_wake_word.assert_called_once()
    mock_audio_input.assert_called_once()
    mock_audio_output.assert_called_once()
    mock_stt.assert_called_once()
    mock_tts.assert_called_once()
    mock_conversation.assert_called_once()
    mock_filler_manager.assert_called_once()

    # Should start in IDLE state
    assert jf.state == ConversationState.IDLE


def test_conversation_state_enum():
    """Test ConversationState enum values."""
    assert ConversationState.IDLE.value == "idle"
    assert ConversationState.LISTENING.value == "listening"
    assert ConversationState.PROCESSING.value == "processing"
    assert ConversationState.SPEAKING.value == "speaking"


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_state_transition_idle_to_listening(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test state transition from IDLE to LISTENING on wake word."""
    mock_get_personality.return_value = mock_personality
    mock_wake_instance = mock_wake_word.return_value

    jf = JFSebastian(personality_name="johnny")

    # Simulate wake word detection
    jf._on_wake_word_detected()

    # Should transition to LISTENING
    assert jf.state == ConversationState.LISTENING


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_state_transition_listening_to_processing(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test state transition from LISTENING to PROCESSING on speech end."""
    mock_get_personality.return_value = mock_personality
    mock_filler_instance = mock_filler_manager.return_value
    mock_filler_instance.has_fillers = True
    mock_filler_instance.get_random_filler.return_value = (
        Path("/fake/filler.wav"),
        16000,
        "Let me think about that..."
    )

    jf = JFSebastian(personality_name="johnny")
    jf.state = ConversationState.LISTENING

    # Simulate speech end (silence detected)
    jf._on_speech_end()

    # Should transition to PROCESSING
    assert jf.state == ConversationState.PROCESSING


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_filler_selection_before_processing(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test that filler is selected BEFORE transitioning to PROCESSING."""
    mock_get_personality.return_value = mock_personality
    mock_filler_instance = mock_filler_manager.return_value
    mock_filler_instance.has_fillers = True

    test_filler = (Path("/fake/filler.wav"), 16000, "Let me check that...")
    mock_filler_instance.get_random_filler.return_value = test_filler

    jf = JFSebastian(personality_name="johnny")
    jf.state = ConversationState.LISTENING

    # Simulate speech end
    jf._on_speech_end()

    # Filler should be selected
    mock_filler_instance.get_random_filler.assert_called_once()

    # Selected filler should be stored
    assert jf._selected_filler == test_filler


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_cleanup_all_modules(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test that cleanup calls cleanup on all modules."""
    mock_get_personality.return_value = mock_personality

    mock_audio_input_instance = mock_audio_input.return_value
    mock_audio_output_instance = mock_audio_output.return_value
    mock_wake_instance = mock_wake_word.return_value

    jf = JFSebastian(personality_name="johnny")
    jf.cleanup()

    # Should cleanup all modules
    mock_audio_input_instance.cleanup.assert_called_once()
    mock_audio_output_instance.cleanup.assert_called_once()
    mock_wake_instance.cleanup.assert_called_once()


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_context_manager(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test J.F. Sebastian as context manager."""
    mock_get_personality.return_value = mock_personality

    mock_audio_input_instance = mock_audio_input.return_value
    mock_audio_output_instance = mock_audio_output.return_value
    mock_wake_instance = mock_wake_word.return_value

    with JFSebastian(personality_name="johnny") as jf:
        assert jf is not None

    # Should cleanup on exit
    mock_audio_input_instance.cleanup.assert_called_once()
    mock_audio_output_instance.cleanup.assert_called_once()
    mock_wake_instance.cleanup.assert_called_once()


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_no_filler_when_unavailable(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test behavior when no fillers are available."""
    mock_get_personality.return_value = mock_personality
    mock_filler_instance = mock_filler_manager.return_value
    mock_filler_instance.has_fillers = False
    mock_filler_instance.get_random_filler.return_value = None

    jf = JFSebastian(personality_name="johnny")
    jf.state = ConversationState.LISTENING

    # Simulate speech end
    jf._on_speech_end()

    # Should transition to PROCESSING even without filler
    assert jf.state == ConversationState.PROCESSING

    # Selected filler should be None
    assert jf._selected_filler is None


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_personality_loading_error(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality
):
    """Test error handling when personality loading fails."""
    mock_get_personality.side_effect = ValueError("Unknown personality: invalid")

    with pytest.raises(ValueError):
        JFSebastian(personality_name="invalid")


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_state_transitions_sequential(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test complete state transition sequence."""
    mock_get_personality.return_value = mock_personality
    mock_filler_instance = mock_filler_manager.return_value
    mock_filler_instance.has_fillers = True
    mock_filler_instance.get_random_filler.return_value = (
        Path("/fake/filler.wav"),
        16000,
        "One moment..."
    )

    jf = JFSebastian(personality_name="johnny")

    # Start in IDLE
    assert jf.state == ConversationState.IDLE

    # Detect wake word -> LISTENING
    jf._on_wake_word_detected()
    assert jf.state == ConversationState.LISTENING

    # Speech ends -> PROCESSING
    jf._on_speech_end()
    assert jf.state == ConversationState.PROCESSING


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_different_personalities(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test initialization with different personalities."""
    mock_get_personality.return_value = mock_personality

    # Test with Johnny
    jf_johnny = JFSebastian(personality_name="johnny")
    mock_get_personality.assert_called_with("johnny")

    # Test with Rich
    jf_rich = JFSebastian(personality_name="rich")
    mock_get_personality.assert_called_with("rich")


@patch('teddy_ruxpin.main.get_personality')
@patch('teddy_ruxpin.main.WakeWordDetector')
@patch('teddy_ruxpin.main.AudioInput')
@patch('teddy_ruxpin.main.AudioOutput')
@patch('teddy_ruxpin.main.SpeechToText')
@patch('teddy_ruxpin.main.Conversation')
@patch('teddy_ruxpin.main.TextToSpeech')
@patch('teddy_ruxpin.main.AnimatronicControlGenerator')
@patch('teddy_ruxpin.main.FillerManager')
def test_filler_context_passed_to_conversation(
    mock_filler_manager, mock_control_gen, mock_tts, mock_conversation,
    mock_stt, mock_audio_output, mock_audio_input, mock_wake_word, mock_get_personality,
    mock_personality
):
    """Test that filler context is available for LLM instruction."""
    mock_get_personality.return_value = mock_personality
    mock_filler_instance = mock_filler_manager.return_value
    mock_filler_instance.has_fillers = True

    filler_text = "Let me check the data real quick..."
    test_filler = (Path("/fake/filler.wav"), 16000, filler_text)
    mock_filler_instance.get_random_filler.return_value = test_filler

    jf = JFSebastian(personality_name="johnny")
    jf.state = ConversationState.LISTENING

    # Simulate speech end
    jf._on_speech_end()

    # Filler text should be stored and available
    assert jf._selected_filler is not None
    assert jf._selected_filler[2] == filler_text
