#!/usr/bin/env python3
"""
Generate pre-recorded filler phrase WAV files for the selected personality.
Run this script to create all filler audio files with PPM control tracks.
"""

import sys
import logging
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teddy_ruxpin.config import settings
from teddy_ruxpin.personalities import get_personality
from teddy_ruxpin.modules.text_to_speech import TextToSpeech
from teddy_ruxpin.modules.animatronic_control import AnimatronicControlGenerator, save_stereo_wav

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def generate_filler_files(personality, output_dir: Path):
    """
    Generate all filler phrase WAV files for a personality.

    Args:
        personality: Personality instance with filler phrases and voice
        output_dir: Directory to save filler WAV files
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get filler phrases and voice from personality
    filler_phrases = personality.filler_phrases
    voice = personality.tts_voice

    # Initialize TTS and control generator with personality's voice
    logger.info("Initializing TTS and animatronic control...")
    tts = TextToSpeech(voice=voice)
    control_gen = AnimatronicControlGenerator()

    # Generate each filler phrase
    for idx, phrase in enumerate(filler_phrases, start=1):
        logger.info(f"Generating filler {idx}/{len(filler_phrases)}: '{phrase[:60]}...'")

        try:
            # Generate TTS audio
            voice_audio_mp3 = tts.synthesize(phrase)
            if not voice_audio_mp3:
                logger.error(f"Failed to generate TTS for phrase {idx}")
                continue

            # Create stereo output with PPM control
            result = control_gen.create_stereo_output(voice_audio_mp3, phrase)
            if not result:
                logger.error(f"Failed to create stereo output for phrase {idx}")
                continue

            stereo_audio, sample_rate = result

            # Save to WAV file
            output_file = output_dir / f"filler_{idx:02d}.wav"
            save_stereo_wav(stereo_audio, sample_rate, str(output_file))
            logger.info(f"Saved: {output_file.name}")

        except Exception as e:
            logger.error(f"Error generating filler {idx}: {e}", exc_info=True)
            continue

    logger.info(f"Filler generation complete! {len(list(output_dir.glob('filler_*.wav')))} files created")


def main():
    """Main entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Generate filler phrase audio files for a personality"
    )
    parser.add_argument(
        "--personality",
        type=str,
        default=settings.PERSONALITY,
        choices=["johnny", "rich"],
        help="Personality to generate fillers for (default: from .env)"
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Filler Phrase Generator")
    logger.info("=" * 80)

    # Validate configuration
    errors = settings.validate()
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    # Load personality from command-line argument
    try:
        personality = get_personality(args.personality)
        logger.info(f"Personality: {personality.name}")
        logger.info(f"TTS Voice: {personality.tts_voice}")
        logger.info(f"Filler count: {len(personality.filler_phrases)}")
    except ValueError as e:
        logger.error(f"Failed to load personality: {e}")
        sys.exit(1)

    # Set output directory to personality's filler_audio directory
    output_dir = personality.filler_audio_dir

    logger.info(f"Output directory: {output_dir}")
    logger.info("")

    # Generate fillers
    generate_filler_files(personality, output_dir)

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"Done! Filler phrases for {personality.name} are ready to use.")
    logger.info(f"Location: {output_dir}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
