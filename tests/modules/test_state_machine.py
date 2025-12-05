"""
Tests for state machine module.
"""

import pytest
import time
import threading
from teddy_ruxpin.modules.state_machine import (
    StateMachine,
    ConversationState,
    StateTransition
)


def test_state_machine_initialization():
    """Test StateMachine initialization."""
    sm = StateMachine()

    assert sm.state == ConversationState.IDLE
    assert sm.idle_duration >= 0
    assert sm.conversation_duration is None
    assert sm.last_activity_time > 0


def test_state_machine_valid_idle_to_listening():
    """Test valid transition from IDLE to LISTENING."""
    sm = StateMachine()

    result = sm.transition_to(ConversationState.LISTENING, trigger="wake_word")

    assert result is True
    assert sm.state == ConversationState.LISTENING
    assert sm.conversation_duration is not None
    assert sm.conversation_duration >= 0


def test_state_machine_valid_listening_to_processing():
    """Test valid transition from LISTENING to PROCESSING."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)

    result = sm.transition_to(ConversationState.PROCESSING, trigger="speech_captured")

    assert result is True
    assert sm.state == ConversationState.PROCESSING


def test_state_machine_valid_processing_to_speaking():
    """Test valid transition from PROCESSING to SPEAKING."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.PROCESSING)

    result = sm.transition_to(ConversationState.SPEAKING, trigger="response_ready")

    assert result is True
    assert sm.state == ConversationState.SPEAKING


def test_state_machine_valid_speaking_to_idle():
    """Test valid transition from SPEAKING to IDLE."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.PROCESSING)
    sm.transition_to(ConversationState.SPEAKING)

    result = sm.transition_to(ConversationState.IDLE, trigger="response_complete")

    assert result is True
    assert sm.state == ConversationState.IDLE
    assert sm.conversation_duration is None


def test_state_machine_valid_listening_to_idle():
    """Test valid transition from LISTENING to IDLE (timeout)."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)

    result = sm.transition_to(ConversationState.IDLE, trigger="timeout")

    assert result is True
    assert sm.state == ConversationState.IDLE


def test_state_machine_valid_processing_to_idle():
    """Test valid transition from PROCESSING to IDLE (error)."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.PROCESSING)

    result = sm.transition_to(ConversationState.IDLE, trigger="error")

    assert result is True
    assert sm.state == ConversationState.IDLE


def test_state_machine_invalid_idle_to_processing():
    """Test invalid transition from IDLE to PROCESSING."""
    sm = StateMachine()

    result = sm.transition_to(ConversationState.PROCESSING, trigger="invalid")

    assert result is False
    assert sm.state == ConversationState.IDLE


def test_state_machine_invalid_idle_to_speaking():
    """Test invalid transition from IDLE to SPEAKING."""
    sm = StateMachine()

    result = sm.transition_to(ConversationState.SPEAKING, trigger="invalid")

    assert result is False
    assert sm.state == ConversationState.IDLE


def test_state_machine_invalid_listening_to_speaking():
    """Test invalid transition from LISTENING to SPEAKING."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)

    result = sm.transition_to(ConversationState.SPEAKING, trigger="invalid")

    assert result is False
    assert sm.state == ConversationState.LISTENING


def test_state_machine_invalid_speaking_to_processing():
    """Test invalid transition from SPEAKING to PROCESSING."""
    sm = StateMachine()
    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.PROCESSING)
    sm.transition_to(ConversationState.SPEAKING)

    result = sm.transition_to(ConversationState.PROCESSING, trigger="invalid")

    assert result is False
    assert sm.state == ConversationState.SPEAKING


def test_state_machine_same_state_transition():
    """Test same-state transition (no-op)."""
    sm = StateMachine()

    result = sm.transition_to(ConversationState.IDLE, trigger="no_op")

    assert result is True
    assert sm.state == ConversationState.IDLE


def test_state_machine_activity_timer():
    """Test activity timer updates."""
    sm = StateMachine()

    initial_time = sm.last_activity_time
    time.sleep(0.1)

    sm.transition_to(ConversationState.LISTENING)

    assert sm.last_activity_time > initial_time


def test_state_machine_idle_duration():
    """Test idle duration calculation."""
    sm = StateMachine()

    time.sleep(0.1)

    assert sm.idle_duration >= 0.1


def test_state_machine_reset_activity_timer():
    """Test resetting activity timer."""
    sm = StateMachine()

    time.sleep(0.1)
    initial_idle = sm.idle_duration

    sm.reset_activity_timer()
    time.sleep(0.05)

    assert sm.idle_duration < initial_idle


def test_state_machine_conversation_duration_tracking():
    """Test conversation duration tracking."""
    sm = StateMachine()

    # No conversation yet
    assert sm.conversation_duration is None

    # Start conversation
    sm.transition_to(ConversationState.LISTENING)
    assert sm.conversation_duration is not None
    assert sm.conversation_duration >= 0

    time.sleep(0.1)

    # Should still be tracking
    assert sm.conversation_duration >= 0.1

    # End conversation
    sm.transition_to(ConversationState.IDLE)
    assert sm.conversation_duration is None


def test_state_machine_callback_registration():
    """Test callback registration."""
    sm = StateMachine()
    callback_executed = []

    def test_callback():
        callback_executed.append(True)

    sm.register_callback(ConversationState.LISTENING, test_callback)
    sm.transition_to(ConversationState.LISTENING)

    assert len(callback_executed) == 1


def test_state_machine_multiple_callbacks():
    """Test multiple callbacks for same state."""
    sm = StateMachine()
    execution_order = []

    def callback1():
        execution_order.append(1)

    def callback2():
        execution_order.append(2)

    sm.register_callback(ConversationState.LISTENING, callback1)
    sm.register_callback(ConversationState.LISTENING, callback2)

    sm.transition_to(ConversationState.LISTENING)

    assert execution_order == [1, 2]


def test_state_machine_callback_not_executed_on_invalid_transition():
    """Test callbacks not executed on invalid transition."""
    sm = StateMachine()
    callback_executed = []

    def test_callback():
        callback_executed.append(True)

    sm.register_callback(ConversationState.SPEAKING, test_callback)

    # Invalid transition - callback should not execute
    sm.transition_to(ConversationState.SPEAKING)

    assert len(callback_executed) == 0


def test_state_machine_callback_error_handling():
    """Test callback error handling doesn't break state machine."""
    sm = StateMachine()

    def failing_callback():
        raise Exception("Test exception")

    sm.register_callback(ConversationState.LISTENING, failing_callback)

    # Should not raise exception
    result = sm.transition_to(ConversationState.LISTENING)

    assert result is True
    assert sm.state == ConversationState.LISTENING


def test_state_machine_transition_history():
    """Test transition history tracking."""
    sm = StateMachine()

    sm.transition_to(ConversationState.LISTENING, trigger="wake_word")
    sm.transition_to(ConversationState.PROCESSING, trigger="speech")
    sm.transition_to(ConversationState.SPEAKING, trigger="response")

    history = sm.get_transition_history()

    assert len(history) == 3
    assert history[0].to_state == ConversationState.LISTENING
    assert history[0].trigger == "wake_word"
    assert history[1].to_state == ConversationState.PROCESSING
    assert history[2].to_state == ConversationState.SPEAKING


def test_state_machine_transition_history_limit():
    """Test transition history respects limit."""
    sm = StateMachine()

    # Create many transitions
    for i in range(20):
        sm.transition_to(ConversationState.LISTENING)
        sm.transition_to(ConversationState.IDLE)

    history = sm.get_transition_history(limit=5)

    assert len(history) == 5


def test_state_machine_clear_history():
    """Test clearing transition history."""
    sm = StateMachine()

    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.IDLE)

    assert len(sm.get_transition_history()) > 0

    sm.clear_history()

    assert len(sm.get_transition_history()) == 0


def test_state_machine_thread_safety():
    """Test thread-safe state access."""
    sm = StateMachine()
    results = []

    def transition_worker():
        for _ in range(10):
            sm.transition_to(ConversationState.LISTENING)
            time.sleep(0.001)
            sm.transition_to(ConversationState.IDLE)
            results.append(sm.state)

    # Create multiple threads
    threads = [threading.Thread(target=transition_worker) for _ in range(3)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    # All state accesses should have returned valid states
    assert all(isinstance(state, ConversationState) for state in results)


def test_state_machine_repr():
    """Test string representation."""
    sm = StateMachine()

    repr_str = repr(sm)

    assert "StateMachine" in repr_str
    assert "idle" in repr_str
    assert "idle_duration" in repr_str


def test_state_transition_dataclass():
    """Test StateTransition dataclass."""
    transition = StateTransition(
        from_state=ConversationState.IDLE,
        to_state=ConversationState.LISTENING,
        timestamp=time.time(),
        trigger="test"
    )

    assert transition.from_state == ConversationState.IDLE
    assert transition.to_state == ConversationState.LISTENING
    assert transition.trigger == "test"
    assert transition.timestamp > 0


def test_conversation_state_enum_values():
    """Test ConversationState enum values."""
    assert ConversationState.IDLE.value == "idle"
    assert ConversationState.LISTENING.value == "listening"
    assert ConversationState.PROCESSING.value == "processing"
    assert ConversationState.SPEAKING.value == "speaking"


def test_state_machine_full_conversation_flow():
    """Test complete conversation flow."""
    sm = StateMachine()

    # Wake word detected
    assert sm.transition_to(ConversationState.LISTENING, trigger="wake_word")
    assert sm.state == ConversationState.LISTENING
    assert sm.conversation_duration is not None

    # Speech captured
    assert sm.transition_to(ConversationState.PROCESSING, trigger="speech_captured")
    assert sm.state == ConversationState.PROCESSING

    # Response ready
    assert sm.transition_to(ConversationState.SPEAKING, trigger="response_ready")
    assert sm.state == ConversationState.SPEAKING

    # Response complete
    assert sm.transition_to(ConversationState.IDLE, trigger="response_complete")
    assert sm.state == ConversationState.IDLE
    assert sm.conversation_duration is None


def test_state_machine_conversation_timeout_flow():
    """Test conversation timeout flow."""
    sm = StateMachine()

    # Start listening
    sm.transition_to(ConversationState.LISTENING)
    assert sm.conversation_duration is not None

    # Timeout while listening
    sm.transition_to(ConversationState.IDLE, trigger="timeout")
    assert sm.state == ConversationState.IDLE
    assert sm.conversation_duration is None


def test_state_machine_error_flow():
    """Test error handling flow."""
    sm = StateMachine()

    # Start conversation
    sm.transition_to(ConversationState.LISTENING)
    sm.transition_to(ConversationState.PROCESSING)

    # Error during processing
    sm.transition_to(ConversationState.IDLE, trigger="error")
    assert sm.state == ConversationState.IDLE
    assert sm.conversation_duration is None
