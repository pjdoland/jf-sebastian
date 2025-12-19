#!/usr/bin/env python3
"""
Test script to verify PPM channel assignments.
Generates test audio files for each channel to identify which servo each controls.
"""

import sys
import os

# Add parent directory to path so we can import teddy_ruxpin module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.io import wavfile
from jf_sebastian.modules.ppm_generator import PPMGenerator

def generate_channel_test(channel_index, channel_name, sample_rate=44100):
    """
    Generate a test audio file that sweeps one channel while keeping others at ZERO.

    Args:
        channel_index: Which channel to test (0-7)
        channel_name: Name for the output file
        sample_rate: Audio sample rate
    """
    print(f"Generating test for Channel {channel_index + 1} ({channel_name})...")

    # Test duration: 8 seconds
    duration = 8.0
    num_frames = int(duration / (16600 / 1_000_000))  # 60 Hz frames

    # Initialize ALL channels to ZERO (no signal)
    # This should keep servos inactive/unmoved
    channel_values = np.zeros((num_frames, 8), dtype=np.uint8)

    # Only sweep the test channel
    # Pattern: 0 -> 255 -> 0 in 8 seconds
    frames_per_section = num_frames // 4

    # Ramp up from 0 to 255 (0-2 seconds)
    for i in range(frames_per_section):
        value = int(255 * i / frames_per_section)
        channel_values[i, channel_index] = value

    # Hold at 255 (2-4 seconds)
    channel_values[frames_per_section:2*frames_per_section, channel_index] = 255

    # Ramp down from 255 to 0 (4-6 seconds)
    for i in range(frames_per_section):
        value = int(255 * (1 - i / frames_per_section))
        channel_values[2*frames_per_section + i, channel_index] = value

    # Hold at 0 (6-8 seconds) - already zero from initialization

    # Generate PPM signal
    ppm_gen = PPMGenerator(sample_rate=sample_rate)
    ppm_signal = ppm_gen.generate_ppm_signal(duration, channel_values)

    # Create stereo output: LEFT = silence, RIGHT = PPM control
    silence = np.zeros(len(ppm_signal), dtype=np.float32)
    stereo_audio = np.column_stack((silence, ppm_signal))

    # Convert to int16 for WAV
    audio_int16 = (stereo_audio * 32767).astype(np.int16)

    # Save WAV file
    filename = f"debug_audio/channel_test_{channel_index + 1}_{channel_name}.wav"
    wavfile.write(filename, sample_rate, audio_int16)
    print(f"  Saved: {filename}")
    print(f"  Instructions: Play this file and observe WHICH servo moves")
    print(f"    - 0-2 sec: Servo ramps from minimum to maximum")
    print(f"    - 2-4 sec: Servo holds at maximum")
    print(f"    - 4-6 sec: Servo ramps from maximum to minimum")
    print(f"    - 6-8 sec: Servo holds at minimum (no movement)")
    print(f"    - ONLY ONE servo should move per test!")
    print()


def generate_all_channel_tests():
    """Generate test files for all channels."""
    print("=" * 80)
    print("PPM Channel Test Generator")
    print("=" * 80)
    print()
    print("This script generates test audio files to verify which channel controls")
    print("which servo on your animatronic.")
    print()
    print("Each file tests one channel by sweeping it through its range while keeping")
    print("other channels at neutral (127).")
    print()
    print("Play each file on your animatronic and note which servo moves.")
    print()

    # Define channel names based on expected mapping
    channels = [
        (0, "unused"),
        (1, "eyes"),
        (2, "upper_jaw"),
        (3, "lower_jaw"),
        (4, "reserved_4"),
        (5, "reserved_5"),
        (6, "reserved_6"),
        (7, "reserved_7"),
    ]

    for channel_index, channel_name in channels:
        generate_channel_test(channel_index, channel_name)

    print("=" * 80)
    print("Test files generated!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Play each channel_test_*.wav file on your Teddy Ruxpin")
    print("2. Note which servo moves for EACH file (only ONE servo should move per file)")
    print("3. Report back which channel controls which servo")
    print()
    print("Expected behavior:")
    print("  - All channels except the test channel are set to 0 (minimum/inactive)")
    print("  - ONLY the servo controlled by the test channel should move")
    print("  - If multiple servos move, the channel mapping assumptions are wrong")
    print()
    print("Test pattern for each file:")
    print("  0-2 sec: Servo ramps from 0 to 255 (minimum to maximum)")
    print("  2-4 sec: Servo holds at 255 (maximum position)")
    print("  4-6 sec: Servo ramps from 255 to 0 (maximum to minimum)")
    print("  6-8 sec: Servo holds at 0 (minimum position)")
    print()


if __name__ == "__main__":
    import os

    # Ensure debug_audio directory exists
    os.makedirs("debug_audio", exist_ok=True)

    generate_all_channel_tests()
