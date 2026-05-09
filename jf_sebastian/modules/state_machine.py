"""
State machine for managing conversation flow.
States: IDLE, LISTENING, PROCESSING, SPEAKING
"""

import logging
import time
import threading
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """Conversation states for the Teddy Ruxpin system."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class StateTransition:
    """Represents a state transition event."""
    from_state: ConversationState
    to_state: ConversationState
    timestamp: float
    trigger: str


class StateMachine:
    """
    Manages conversation state transitions and callbacks.
    Thread-safe state management with event-based transitions.
    """

    VALID_TRANSITIONS = {
        ConversationState.IDLE: [ConversationState.LISTENING],
        ConversationState.LISTENING: [ConversationState.PROCESSING, ConversationState.IDLE],
        ConversationState.PROCESSING: [ConversationState.SPEAKING, ConversationState.IDLE],
        ConversationState.SPEAKING: [ConversationState.LISTENING, ConversationState.IDLE],
    }

    def __init__(self):
        self._state: ConversationState = ConversationState.IDLE
        self._lock = threading.Lock()
        self._callbacks: dict[ConversationState, list[Callable]] = {
            state: [] for state in ConversationState
        }
        self._transition_history: list[StateTransition] = []
        self._max_history: int = 100
        self._last_activity_time: float = time.time()
        self._last_transition_time: float = time.time()
        self._conversation_start_time: Optional[float] = None

        logger.info("State machine initialized in IDLE state")

    @property
    def state(self) -> ConversationState:
        """Get current state (thread-safe)."""
        with self._lock:
            return self._state

    @property
    def last_activity_time(self) -> float:
        """Get timestamp of last activity."""
        with self._lock:
            return self._last_activity_time

    @property
    def idle_duration(self) -> float:
        """Get seconds since last activity."""
        return time.time() - self.last_activity_time

    @property
    def conversation_duration(self) -> Optional[float]:
        """Get duration of current conversation session, or None if no active conversation."""
        with self._lock:
            if self._conversation_start_time is None:
                return None
            return time.time() - self._conversation_start_time

    def try_transition(
        self,
        expected_state: ConversationState,
        new_state: ConversationState,
        trigger: str = "manual",
    ) -> bool:
        """
        Atomic compare-and-swap transition. Only transitions if the current
        state matches `expected_state`. Closes the TOCTOU window between
        callers checking `.state` and calling `transition_to(...)`.

        Returns True iff the transition succeeded.
        """
        with self._lock:
            if self._state != expected_state:
                return False
            old_state = self._state
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(
                    f"Invalid state transition: {old_state.value} -> {new_state.value} "
                    f"(trigger: {trigger})"
                )
                return False
            self._state = new_state
            self._last_activity_time = time.time()
            self._last_transition_time = time.time()
            if new_state == ConversationState.LISTENING and old_state == ConversationState.IDLE:
                self._conversation_start_time = time.time()
                logger.info("New conversation session started")
            elif new_state == ConversationState.IDLE:
                self._conversation_start_time = None
                logger.info("Conversation session ended")
            transition = StateTransition(
                from_state=old_state,
                to_state=new_state,
                timestamp=time.time(),
                trigger=trigger,
            )
            self._transition_history.append(transition)
            if len(self._transition_history) > self._max_history:
                self._transition_history = self._transition_history[-self._max_history:]
            logger.info(
                f"State transition: {old_state.value} -> {new_state.value} (trigger: {trigger})"
            )
        self._execute_callbacks(new_state)
        return True

    def transition_to(self, new_state: ConversationState, trigger: str = "manual") -> bool:
        """
        Transition to a new state if valid.

        Args:
            new_state: Target state
            trigger: Description of what triggered the transition

        Returns:
            True if transition was successful, False if invalid
        """
        with self._lock:
            old_state = self._state

            # Validate transition
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(
                    f"Invalid state transition: {old_state.value} -> {new_state.value} "
                    f"(trigger: {trigger})"
                )
                return False

            # Perform transition
            self._state = new_state
            self._last_activity_time = time.time()
            self._last_transition_time = time.time()  # Track transition time for recovery

            # Track conversation session
            if new_state == ConversationState.LISTENING and old_state == ConversationState.IDLE:
                self._conversation_start_time = time.time()
                logger.info("New conversation session started")
            elif new_state == ConversationState.IDLE:
                self._conversation_start_time = None
                logger.info("Conversation session ended")

            # Record transition (cap history to prevent unbounded growth)
            transition = StateTransition(
                from_state=old_state,
                to_state=new_state,
                timestamp=time.time(),
                trigger=trigger
            )
            self._transition_history.append(transition)
            if len(self._transition_history) > self._max_history:
                self._transition_history = self._transition_history[-self._max_history:]

            logger.info(
                f"State transition: {old_state.value} -> {new_state.value} "
                f"(trigger: {trigger})"
            )

        # Execute callbacks outside of lock to prevent deadlock
        self._execute_callbacks(new_state)
        return True

    def _is_valid_transition(self, from_state: ConversationState, to_state: ConversationState) -> bool:
        """Check if a state transition is valid."""
        # Allow same-state "transitions" (no-op)
        if from_state == to_state:
            return True

        return to_state in self.VALID_TRANSITIONS.get(from_state, [])

    def register_callback(self, state: ConversationState, callback: Callable):
        """
        Register a callback to be executed when entering a state.

        Args:
            state: State to trigger callback on
            callback: Function to call (should be non-blocking or threaded)
        """
        with self._lock:
            self._callbacks[state].append(callback)
        logger.debug(f"Registered callback for state: {state.value}")

    def _execute_callbacks(self, state: ConversationState):
        """Execute all callbacks for a given state."""
        callbacks = self._callbacks[state].copy()
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error executing callback for state {state.value}: {e}", exc_info=True)

    def reset_activity_timer(self):
        """Reset the activity timer (useful for extending timeout periods)."""
        with self._lock:
            self._last_activity_time = time.time()

    def get_transition_history(self, limit: int = 10) -> list[StateTransition]:
        """Get recent state transitions."""
        with self._lock:
            return self._transition_history[-limit:]

    def clear_history(self):
        """Clear transition history (useful for debugging/testing)."""
        with self._lock:
            self._transition_history.clear()
        logger.debug("Transition history cleared")

    def __repr__(self) -> str:
        return f"StateMachine(state={self.state.value}, idle_duration={self.idle_duration:.1f}s)"
