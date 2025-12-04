#!/usr/bin/env python3
"""
Simple microphone test to verify audio input is working.
"""

import pyaudio
import numpy as np
import time

# Audio settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 512
INPUT_DEVICE_INDEX = 2  # MacBook Air Microphone

print("=" * 80)
print("Microphone Test")
print("=" * 80)
print(f"Using device index: {INPUT_DEVICE_INDEX}")
print("Speak into your microphone...")
print("You should see volume levels appear below.")
print("Press Ctrl+C to stop.")
print("=" * 80)
print()

p = pyaudio.PyAudio()

try:
    # Open microphone stream
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        input_device_index=INPUT_DEVICE_INDEX,
    )

    print("✓ Microphone opened successfully!")
    print()

    # Read and display audio levels
    for i in range(100):  # Run for ~10 seconds
        try:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            audio_array = np.frombuffer(data, dtype=np.int16)

            # Calculate RMS volume
            rms = np.sqrt(np.mean(audio_array**2))

            # Scale to 0-50 for display
            volume = int(rms / 1000 * 50)
            volume = min(volume, 50)

            # Display volume bar
            bar = "█" * volume + "░" * (50 - volume)
            print(f"\rVolume: {bar} {int(rms):5d}", end="", flush=True)

            time.sleep(0.1)

        except KeyboardInterrupt:
            break

    print("\n\n✓ Test complete!")

    stream.stop_stream()
    stream.close()

except Exception as e:
    print(f"✗ Error: {e}")
    print()
    print("Troubleshooting:")
    print("1. Check System Settings > Privacy & Security > Microphone")
    print("2. Ensure Terminal has microphone access")
    print("3. Try running: python test_microphone.py")

finally:
    p.terminate()
