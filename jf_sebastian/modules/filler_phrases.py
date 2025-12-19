"""
Filler phrase system for low-latency responses.
Pre-generates short phrases that play immediately while real response is prepared.
"""

import logging
import random
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class FillerPhraseManager:
    """
    Manages pre-generated filler phrases for low-latency responses.
    """

    def __init__(self, filler_dir: Path, filler_phrases: list[str]):
        """
        Initialize filler phrase manager.

        Args:
            filler_dir: Directory containing pre-generated filler WAV files
            filler_phrases: List of filler phrase texts for this personality
        """
        self.filler_dir = Path(filler_dir)
        self.filler_phrases = filler_phrases
        self.filler_files = []
        self._load_filler_files()

    def _load_filler_files(self):
        """Load list of available filler files."""
        if not self.filler_dir.exists():
            logger.warning(f"Filler directory does not exist: {self.filler_dir}")
            logger.warning("Run generate_fillers.py to create filler phrases")
            return

        self.filler_files = sorted(self.filler_dir.glob("filler_*.wav"))
        logger.info(f"Loaded {len(self.filler_files)} filler phrases from {self.filler_dir}")

    def get_random_filler(self) -> Optional[Tuple[np.ndarray, int, str]]:
        """
        Get a random filler phrase audio with its text.

        Returns:
            Tuple of (stereo_audio, sample_rate, filler_text) or None if no fillers available
        """
        if not self.filler_files:
            logger.warning("No filler files available")
            return None

        # Pick random filler
        filler_file = random.choice(self.filler_files)

        # Extract index from filename (e.g., filler_01.wav -> 0)
        try:
            filler_index = int(filler_file.stem.split('_')[1]) - 1
            filler_text = self.filler_phrases[filler_index] if 0 <= filler_index < len(self.filler_phrases) else ""
        except:
            filler_text = ""

        logger.debug(f"Selected filler: {filler_file.name}")

        try:
            # Load WAV file
            from scipy.io import wavfile
            sample_rate, audio_data = wavfile.read(filler_file)

            # Ensure it's float32 normalized to -1 to 1
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_data = audio_data.astype(np.float32) / 2147483648.0

            logger.info(f"Loaded filler: {filler_file.name} ({audio_data.shape[0]} samples at {sample_rate}Hz)")
            return audio_data, sample_rate, filler_text

        except Exception as e:
            logger.error(f"Error loading filler file {filler_file}: {e}", exc_info=True)
            return None

    @property
    def has_fillers(self) -> bool:
        """Check if any filler files are available."""
        return len(self.filler_files) > 0
