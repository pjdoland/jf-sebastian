"""
Async file utilities for non-blocking debug file saves.
Saves happen in background threads to not block the main pipeline.
"""

import logging
import threading
from pathlib import Path
from typing import Callable, Any

logger = logging.getLogger(__name__)


def save_async(save_func: Callable, *args, **kwargs) -> None:
    """
    Execute a save function in a background thread (non-blocking).

    Args:
        save_func: Function to call for saving (e.g., save_audio_to_wav)
        *args: Positional arguments to pass to save_func
        **kwargs: Keyword arguments to pass to save_func

    Example:
        save_async(save_audio_to_wav, audio_data, "debug.wav")
        # Returns immediately, save happens in background
    """
    def _save_worker():
        try:
            save_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Async save failed: {e}")

    # Start save in background thread (daemon so it doesn't block shutdown)
    thread = threading.Thread(target=_save_worker, daemon=True)
    thread.start()
