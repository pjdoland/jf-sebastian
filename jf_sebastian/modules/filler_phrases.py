"""
Filler phrase system for low-latency responses.
Pre-generates short phrases that play immediately while real response is prepared.
"""

import logging
import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


class FillerPhraseManager:
    """
    Catalogs pre-generated filler phrase audio files on disk and decodes one
    on demand. Reads happen during PROCESSING, not the real-time playback
    path, so the few-ms NVMe decode is invisible to the user.
    """

    def __init__(self, filler_dir: Path, filler_phrases: list[str], device_type: str):
        """
        Args:
            filler_dir: Base directory containing device-specific filler subdirectories
            filler_phrases: List of filler phrase texts for this personality
            device_type: Output device type (e.g., 'teddy_ruxpin', 'squawkers_mccaw')
        """
        self.filler_base_dir = Path(filler_dir)
        self.device_type = device_type
        self.filler_dir = self.filler_base_dir / device_type
        self.filler_phrases = filler_phrases
        self.filler_entries: list[Tuple[Path, str]] = []
        self._scan_filler_files()

    def _scan_filler_files(self):
        if not self.filler_dir.exists():
            logger.warning(f"Device-specific filler directory does not exist: {self.filler_dir}")
            logger.warning(f"Run scripts/generate_fillers.py to create filler phrases for {self.device_type}")
            return

        for filler_file in sorted(self.filler_dir.glob("filler_*.wav")):
            try:
                phrase_index = int(filler_file.stem.split('_')[1]) - 1
                filler_text = self.filler_phrases[phrase_index] if 0 <= phrase_index < len(self.filler_phrases) else ""
                self.filler_entries.append((filler_file, filler_text))
            except (ValueError, IndexError) as e:
                logger.warning(f"Skipping malformed filler filename {filler_file.name}: {e}")
                continue

        logger.info(f"Catalogued {len(self.filler_entries)} filler phrases for {self.device_type} (lazy-loaded)")

    def get_random_filler(self) -> Optional[Tuple[np.ndarray, int, str]]:
        """
        Pick a random filler and load it from disk now.

        Returns:
            Tuple of (stereo_audio, sample_rate, filler_text) or None if no fillers available
        """
        if not self.filler_entries:
            logger.warning("No filler phrases available")
            return None

        filler_path, filler_text = random.choice(self.filler_entries)

        try:
            audio_data, sample_rate = sf.read(str(filler_path), dtype='float32')
        except Exception as e:
            logger.warning(f"Failed to load filler {filler_path.name}: {e}")
            return None

        logger.debug(f"Loaded filler: {len(audio_data)} samples from {filler_path.name}, {filler_text[:50]}...")
        return audio_data, sample_rate, filler_text

    @property
    def has_fillers(self) -> bool:
        return len(self.filler_entries) > 0
