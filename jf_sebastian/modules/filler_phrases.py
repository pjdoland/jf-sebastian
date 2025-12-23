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
    Pre-loads all filler audio into memory at startup for instant access.
    """

    def __init__(self, filler_dir: Path, filler_phrases: list[str], device_type: str):
        """
        Initialize filler phrase manager and pre-load all filler audio.

        Args:
            filler_dir: Base directory containing device-specific filler subdirectories
            filler_phrases: List of filler phrase texts for this personality
            device_type: Output device type (e.g., 'teddy_ruxpin', 'squawkers_mccaw')
        """
        self.filler_base_dir = Path(filler_dir)
        self.device_type = device_type
        self.filler_dir = self.filler_base_dir / device_type
        self.filler_phrases = filler_phrases
        self.filler_cache = []  # Pre-loaded (audio, sample_rate, text) tuples
        self._load_filler_files()

    def _load_filler_files(self):
        """Pre-load all filler audio files into memory for instant access."""
        if not self.filler_dir.exists():
            logger.warning(f"Device-specific filler directory does not exist: {self.filler_dir}")
            logger.warning(f"Run scripts/generate_fillers.py to create filler phrases for {self.device_type}")
            return

        filler_files = sorted(self.filler_dir.glob("filler_*.wav"))

        logger.info(f"Pre-loading {len(filler_files)} filler phrases for {self.device_type}...")

        try:
            import soundfile as sf
            use_soundfile = True
        except ImportError:
            logger.warning("soundfile not available, falling back to scipy.wavfile (slower)")
            from scipy.io import wavfile
            use_soundfile = False

        for filler_file in filler_files:
            try:
                # Extract index from filename (e.g., filler_01.wav -> 0)
                filler_index = int(filler_file.stem.split('_')[1]) - 1
                filler_text = self.filler_phrases[filler_index] if 0 <= filler_index < len(self.filler_phrases) else ""

                # Load WAV file into memory (soundfile is much faster and handles metadata chunks)
                if use_soundfile:
                    audio_data, sample_rate = sf.read(str(filler_file), dtype='float32')
                else:
                    sample_rate, audio_data = wavfile.read(filler_file)
                    # Ensure it's float32 normalized to -1 to 1
                    if audio_data.dtype == np.int16:
                        audio_data = audio_data.astype(np.float32) / 32768.0
                    elif audio_data.dtype == np.int32:
                        audio_data = audio_data.astype(np.float32) / 2147483648.0

                # Store in cache
                self.filler_cache.append((audio_data, sample_rate, filler_text))

            except Exception as e:
                logger.warning(f"Failed to load filler {filler_file.name}: {e}")
                continue

        logger.info(f"Pre-loaded {len(self.filler_cache)} filler phrases into memory")

    def get_random_filler(self) -> Optional[Tuple[np.ndarray, int, str]]:
        """
        Get a random pre-loaded filler phrase (instant, no disk I/O).

        Returns:
            Tuple of (stereo_audio, sample_rate, filler_text) or None if no fillers available
        """
        if not self.filler_cache:
            logger.warning("No filler phrases available in cache")
            return None

        # Pick random filler from pre-loaded cache (instant!)
        audio_data, sample_rate, filler_text = random.choice(self.filler_cache)

        logger.debug(f"Selected filler: {len(audio_data)} samples, {filler_text[:50]}...")

        return audio_data, sample_rate, filler_text

    @property
    def has_fillers(self) -> bool:
        """Check if any filler phrases are available."""
        return len(self.filler_cache) > 0
