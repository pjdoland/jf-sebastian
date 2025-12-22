#!/usr/bin/env python3
"""
RVC Optimization Testing Script

Tests different RVC parameter combinations to find the best balance
between speed and quality for Dale Gribble voice conversion.

Usage:
    python test_rvc_optimization.py
"""

import sys
import time
import logging
from pathlib import Path
import numpy as np
import soundfile as sf

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from jf_sebastian.modules.rvc_processor import RVCProcessor
from jf_sebastian.config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configurations - from conservative to aggressive
TEST_CONFIGS = [
    {
        'name': 'Current (Conservative)',
        'f0_method': 'pm',
        'filter_radius': 3,
        'rms_mix_rate': 0.25,
        'protect': 0.33,
        'index_rate': 0.5,
    },
    {
        'name': 'Optimized (Balanced)',
        'f0_method': 'pm',
        'filter_radius': 1,
        'rms_mix_rate': 0.15,
        'protect': 0.25,
        'index_rate': 0.4,
    },
    {
        'name': 'Fast (Aggressive)',
        'f0_method': 'pm',
        'filter_radius': 0,
        'rms_mix_rate': 0.1,
        'protect': 0.2,
        'index_rate': 0.3,
    },
    {
        'name': 'RMVPE (Alternative F0)',
        'f0_method': 'rmvpe',
        'filter_radius': 1,
        'rms_mix_rate': 0.15,
        'protect': 0.25,
        'index_rate': 0.4,
    },
]

# Model paths
MODEL_PATH = Path('personalities/leopold/DaleGribbleKOTH.pth')
INDEX_PATH = None  # Add if you have an index file


def create_test_audio():
    """Create or use existing test audio."""
    # Check for existing debug audio
    debug_path = Path('debug_audio')
    if debug_path.exists():
        # Find a recent rvc_input file
        input_files = sorted(debug_path.glob('rvc_input_*.wav'))
        if input_files:
            logger.info(f"Using existing test audio: {input_files[-1]}")
            audio, sr = sf.read(str(input_files[-1]))
            return audio, sr

    # Generate simple test audio if no debug files exist
    logger.info("Generating test audio (1 second sine wave)")
    duration = 1.0
    sample_rate = 16000
    frequency = 440.0  # A4 note
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = 0.5 * np.sin(2 * np.pi * frequency * t)
    return audio.astype(np.float32), sample_rate


def test_rvc_config(processor, audio, sample_rate, config, output_dir):
    """Test a single RVC configuration."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing: {config['name']}")
    logger.info(f"Parameters: {config}")
    logger.info(f"{'='*60}")

    # Measure conversion time
    start_time = time.time()

    try:
        converted = processor.convert_audio(
            audio=audio,
            sample_rate=sample_rate,
            model_path=str(MODEL_PATH),
            index_path=str(INDEX_PATH) if INDEX_PATH else None,
            pitch_shift=0,
            f0_method=config['f0_method'],
            filter_radius=config['filter_radius'],
            rms_mix_rate=config['rms_mix_rate'],
            protect=config['protect'],
            index_rate=config['index_rate'],
        )

        elapsed = time.time() - start_time

        if converted is None:
            logger.error(f"Conversion failed for {config['name']}")
            return None

        # Save output
        output_file = output_dir / f"{config['name'].lower().replace(' ', '_').replace('(', '').replace(')', '')}.wav"
        sf.write(str(output_file), converted, 48000, subtype='FLOAT')

        # Calculate audio statistics
        rms = np.sqrt(np.mean(converted**2))
        peak = np.max(np.abs(converted))

        result = {
            'name': config['name'],
            'time': elapsed,
            'rms': rms,
            'peak': peak,
            'output_file': output_file,
            'config': config,
        }

        logger.info(f"✓ Completed in {elapsed:.2f}s")
        logger.info(f"  RMS: {rms:.4f}, Peak: {peak:.4f}")
        logger.info(f"  Output: {output_file}")

        return result

    except Exception as e:
        logger.error(f"Error testing {config['name']}: {e}", exc_info=True)
        return None


def main():
    """Run RVC optimization tests."""
    logger.info("RVC Optimization Test Suite")
    logger.info(f"Model: {MODEL_PATH}")
    logger.info(f"Device: {settings.RVC_DEVICE}")

    # Check if model exists
    if not MODEL_PATH.exists():
        logger.error(f"Model not found: {MODEL_PATH}")
        logger.info("Please ensure DaleGribbleKOTH.pth is in personalities/leopold/")
        return

    # Create output directory
    output_dir = Path('rvc_optimization_tests')
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Output directory: {output_dir}")

    # Initialize RVC processor
    logger.info(f"Initializing RVC processor (device={settings.RVC_DEVICE})...")
    processor = RVCProcessor(device=settings.RVC_DEVICE)

    if not processor.available:
        logger.error("RVC processor not available")
        return

    # Get test audio
    logger.info("Preparing test audio...")
    audio, sample_rate = create_test_audio()
    logger.info(f"Test audio: {len(audio)} samples @ {sample_rate}Hz ({len(audio)/sample_rate:.2f}s)")

    # Save input audio for reference
    input_file = output_dir / 'input.wav'
    sf.write(str(input_file), audio, sample_rate, subtype='PCM_16')
    logger.info(f"Saved input: {input_file}")

    # Run tests
    results = []
    for config in TEST_CONFIGS:
        result = test_rvc_config(processor, audio, sample_rate, config, output_dir)
        if result:
            results.append(result)
        time.sleep(1)  # Brief pause between tests

    # Generate report
    logger.info(f"\n{'='*80}")
    logger.info("TEST RESULTS SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"{'Configuration':<30} {'Time (s)':<12} {'Speedup':<12} {'RMS':<12} {'Peak':<12}")
    logger.info(f"{'-'*80}")

    if results:
        baseline_time = results[0]['time']

        for result in results:
            speedup = baseline_time / result['time']
            logger.info(
                f"{result['name']:<30} "
                f"{result['time']:<12.2f} "
                f"{speedup:<12.2f}x "
                f"{result['rms']:<12.4f} "
                f"{result['peak']:<12.4f}"
            )

        logger.info(f"{'-'*80}")
        logger.info(f"\nBaseline (Current): {baseline_time:.2f}s")

        # Find fastest
        fastest = min(results, key=lambda r: r['time'])
        logger.info(f"Fastest: {fastest['name']} ({fastest['time']:.2f}s, {baseline_time/fastest['time']:.2f}x speedup)")

        logger.info(f"\n{'='*80}")
        logger.info("NEXT STEPS:")
        logger.info(f"{'='*80}")
        logger.info(f"1. Listen to all files in: {output_dir}/")
        logger.info(f"2. Compare quality vs speed trade-off")
        logger.info(f"3. Choose your preferred configuration")
        logger.info(f"4. Update personalities/leopold/personality.yaml with chosen settings")
        logger.info(f"\nRecommended settings for balanced quality/speed:")
        logger.info(f"---")

        # Recommend the "Optimized (Balanced)" config
        for result in results:
            if 'Balanced' in result['name']:
                config = result['config']
                logger.info(f"rvc_f0_method: {config['f0_method']}")
                logger.info(f"rvc_filter_radius: {config['filter_radius']}")
                logger.info(f"rvc_rms_mix_rate: {config['rms_mix_rate']}")
                logger.info(f"rvc_protect: {config['protect']}")
                logger.info(f"rvc_index_rate: {config['index_rate']}")
                logger.info(f"Expected speedup: ~{baseline_time/result['time']:.1f}x")
                break

        logger.info(f"\n{'='*80}\n")
    else:
        logger.error("No successful test results")


if __name__ == '__main__':
    main()
