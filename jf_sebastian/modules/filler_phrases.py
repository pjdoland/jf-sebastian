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
    Indexes filler audio files on disk and reads one on demand. The previous
    implementation kept all decoded PCM in RAM (>100 MB per personality on
    headless), which is wasted memory on a Jetson — only one filler ever plays
    at a time, the read happens during PROCESSING (not the real-time audio
    path), and NVMe SSDs decode a WAV in a few ms.
    """

    def __init__(self, filler_dir: Path, filler_phrases: list[str], device_type: str):
        """
        Initialize filler phrase manager. Indexes available filler files but
        does not load audio into memory.

        Args:
            filler_dir: Base directory containing device-specific filler subdirectories
            filler_phrases: List of filler phrase texts for this personality
            device_type: Output device type (e.g., 'teddy_ruxpin', 'squawkers_mccaw')
        """
        self.filler_base_dir = Path(filler_dir)
        self.device_type = device_type
        self.filler_dir = self.filler_base_dir / device_type
        self.filler_phrases = filler_phrases
        # List of (file_path, text) tuples — just paths, no audio resident
        self.filler_index: list[Tuple[Path, str]] = []
        self._index_filler_files()

    def _index_filler_files(self):
        """Index filler files on disk without loading audio."""
        if not self.filler_dir.exists():
            logger.warning(f"Device-specific filler directory does not exist: {self.filler_dir}")
            logger.warning(f"Run scripts/generate_fillers.py to create filler phrases for {self.device_type}")
            return

        filler_files = sorted(self.filler_dir.glob("filler_*.wav"))

        for filler_file in filler_files:
            try:
                # Extract index from filename (e.g., filler_01.wav -> 0)
                filler_index = int(filler_file.stem.split('_')[1]) - 1
                filler_text = self.filler_phrases[filler_index] if 0 <= filler_index < len(self.filler_phrases) else ""
                self.filler_index.append((filler_file, filler_text))
            except (ValueError, IndexError) as e:
                logger.warning(f"Skipping malformed filler filename {filler_file.name}: {e}")
                continue

        logger.info(f"Indexed {len(self.filler_index)} filler phrases for {self.device_type} (lazy-loaded)")

    def _read_wav(self, path: Path) -> Tuple[np.ndarray, int]:
        """Read a WAV file as float32 normalized to -1.0..1.0."""
        try:
            import soundfile as sf
            return sf.read(str(path), dtype='float32')
        except ImportError:
            from scipy.io import wavfile
            sample_rate, audio_data = wavfile.read(path)
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_data = audio_data.astype(np.float32) / 2147483648.0
            return audio_data, sample_rate

    def get_random_filler(self) -> Optional[Tuple[np.ndarray, int, str]]:
        """
        Pick a random filler and load it from disk now.

        Returns:
            Tuple of (stereo_audio, sample_rate, filler_text) or None if no fillers available
        """
        if not self.filler_index:
            logger.warning("No filler phrases available")
            return None

        filler_path, filler_text = random.choice(self.filler_index)

        try:
            audio_data, sample_rate = self._read_wav(filler_path)
        except Exception as e:
            logger.warning(f"Failed to load filler {filler_path.name}: {e}")
            return None

        logger.debug(f"Loaded filler: {len(audio_data)} samples from {filler_path.name}, {filler_text[:50]}...")
        return audio_data, sample_rate, filler_text

    @property
    def has_fillers(self) -> bool:
        """Check if any filler phrases are available."""
        return len(self.filler_index) > 0
