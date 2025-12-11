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
from personalities import get_personality, list_personalities
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

    # Initialize TTS and control generator with personality's TTS settings
    logger.info("Initializing TTS and animatronic control...")
    tts = TextToSpeech(
        voice=voice,
        speed=personality.tts_speed,
        style_instruction=personality.tts_style
    )
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
    # Discover available personalities
    available_personalities = list_personalities()

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Generate filler phrase audio files for personalities"
    )
    parser.add_argument(
        "--personality",
        type=str,
        default=None,
        help=f"Personality to generate fillers for. Available: {', '.join(available_personalities)}. "
             f"If not specified, generates for all personalities."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate fillers for all available personalities (same as not specifying --personality)"
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

    # Determine which personalities to process
    if args.personality:
        # Single personality specified
        personalities_to_process = [args.personality]
    else:
        # Generate for all personalities
        personalities_to_process = available_personalities
        logger.info(f"No personality specified - generating for all {len(personalities_to_process)} personalities")
        logger.info("")

    # Process each personality
    for personality_name in personalities_to_process:
        logger.info("=" * 80)
        logger.info(f"Processing: {personality_name}")
        logger.info("=" * 80)

        # Load personality
        try:
            personality = get_personality(personality_name)
            logger.info(f"Personality: {personality.name}")
            logger.info(f"TTS Voice: {personality.tts_voice}")
            logger.info(f"Filler count: {len(personality.filler_phrases)}")
        except ValueError as e:
            logger.error(f"Failed to load personality '{personality_name}': {e}")
            continue

        # Set output directory to personality's filler_audio directory
        output_dir = personality.filler_audio_dir

        logger.info(f"Output directory: {output_dir}")
        logger.info("")

        # Generate fillers
        generate_filler_files(personality, output_dir)

        logger.info("")

    logger.info("=" * 80)
    logger.info("All done!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
