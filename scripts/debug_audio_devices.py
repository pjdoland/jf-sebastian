#!/usr/bin/env python3
"""
Debug script for diagnosing audio device issues.
Lists all audio devices, their supported sample rates, and channel configurations.
Useful for configuring INPUT_DEVICE_NAME and OUTPUT_DEVICE_NAME in .env on new hardware.

Usage:
    python scripts/debug_audio_devices.py
    python scripts/debug_audio_devices.py --test-input 24    # Test recording from device 24
    python scripts/debug_audio_devices.py --test-output 25   # Test playback on device 25
"""

import argparse
import sys
import time
import struct
import math

import pyaudio
import numpy as np


SAMPLE_RATES = [8000, 16000, 22050, 44100, 48000, 96000]
FORMATS = {
    "int16": pyaudio.paInt16,
    "int32": pyaudio.paInt32,
    "float32": pyaudio.paFloat32,
}


def check_supported_rates(p, device_index, direction="input"):
    """Check which sample rates a device supports."""
    supported = []
    info = p.get_device_info_by_index(device_index)

    for rate in SAMPLE_RATES:
        try:
            kwargs = {
                f"{direction}_device": device_index,
                f"{direction}_channels": 1,
                f"{direction}_format": pyaudio.paInt16,
            }
            p.is_format_supported(rate, **kwargs)
            supported.append(rate)
        except ValueError:
            pass
        except Exception:
            pass

    return supported


def check_supported_channels(p, device_index, direction="input"):
    """Check which channel counts a device supports."""
    supported = []
    info = p.get_device_info_by_index(device_index)
    default_rate = int(info["defaultSampleRate"])

    for channels in [1, 2, 4, 6, 8]:
        try:
            kwargs = {
                f"{direction}_device": device_index,
                f"{direction}_channels": channels,
                f"{direction}_format": pyaudio.paInt16,
            }
            p.is_format_supported(default_rate, **kwargs)
            supported.append(channels)
        except ValueError:
            pass
        except Exception:
            pass

    return supported


def check_supported_formats(p, device_index, direction="input"):
    """Check which audio formats a device supports."""
    supported = []
    info = p.get_device_info_by_index(device_index)
    default_rate = int(info["defaultSampleRate"])

    for name, fmt in FORMATS.items():
        try:
            kwargs = {
                f"{direction}_device": device_index,
                f"{direction}_channels": 1,
                f"{direction}_format": fmt,
            }
            p.is_format_supported(default_rate, **kwargs)
            supported.append(name)
        except ValueError:
            pass
        except Exception:
            pass

    return supported


def list_devices(p):
    """List all audio devices with detailed capability info."""
    print("=" * 80)
    print("AUDIO DEVICE REPORT")
    print("=" * 80)

    default_input = p.get_default_input_device_info()
    default_output = p.get_default_output_device_info()

    print(f"\nDefault INPUT device:  [{default_input['index']}] {default_input['name']}")
    print(f"Default OUTPUT device: [{default_output['index']}] {default_output['name']}")

    # Collect devices by type
    input_devices = []
    output_devices = []

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            input_devices.append((i, info))
        if info["maxOutputChannels"] > 0:
            output_devices.append((i, info))

    # Print input devices
    print(f"\n{'─' * 80}")
    print(f"INPUT DEVICES ({len(input_devices)} found)")
    print(f"{'─' * 80}")

    for idx, info in input_devices:
        is_default = " ** DEFAULT **" if idx == default_input["index"] else ""
        is_usb = " [USB]" if "usb" in info["name"].lower() else ""
        print(f"\n  [{idx}] {info['name']}{is_default}{is_usb}")
        print(f"       Max channels: {info['maxInputChannels']}")
        print(f"       Default rate: {int(info['defaultSampleRate'])} Hz")
        print(f"       Input latency: {info['defaultLowInputLatency']*1000:.1f}ms (low) / {info['defaultHighInputLatency']*1000:.1f}ms (high)")

        # Check supported rates
        rates = check_supported_rates(p, idx, "input")
        rate_str = ", ".join(f"{r}Hz" for r in rates) if rates else "none detected"
        needs_16k = "16000" in str(rates)
        print(f"       Supported rates: {rate_str}")
        if not needs_16k and rates:
            print(f"       ⚠  16kHz NOT supported — will need resampling from {rates[0]}Hz")

        # Check supported channels
        channels = check_supported_channels(p, idx, "input")
        print(f"       Supported channels: {channels}")

        # Check supported formats
        formats = check_supported_formats(p, idx, "input")
        print(f"       Supported formats: {formats}")

    # Print output devices
    print(f"\n{'─' * 80}")
    print(f"OUTPUT DEVICES ({len(output_devices)} found)")
    print(f"{'─' * 80}")

    for idx, info in output_devices:
        is_default = " ** DEFAULT **" if idx == default_output["index"] else ""
        is_usb = " [USB]" if "usb" in info["name"].lower() else ""
        print(f"\n  [{idx}] {info['name']}{is_default}{is_usb}")
        print(f"       Max channels: {info['maxOutputChannels']}")
        print(f"       Default rate: {int(info['defaultSampleRate'])} Hz")
        print(f"       Output latency: {info['defaultLowOutputLatency']*1000:.1f}ms (low) / {info['defaultHighOutputLatency']*1000:.1f}ms (high)")

        # Check supported rates
        rates = check_supported_rates(p, idx, "output")
        rate_str = ", ".join(f"{r}Hz" for r in rates) if rates else "none detected"
        print(f"       Supported rates: {rate_str}")

        # Check supported channels
        channels = check_supported_channels(p, idx, "output")
        print(f"       Supported channels: {channels}")

        # Check supported formats
        formats = check_supported_formats(p, idx, "output")
        print(f"       Supported formats: {formats}")

    # Recommendations
    print(f"\n{'─' * 80}")
    print("RECOMMENDATIONS FOR .env")
    print(f"{'─' * 80}")

    # Find best input (prefer USB, then default)
    usb_inputs = [(i, info) for i, info in input_devices if "usb" in info["name"].lower()]
    if usb_inputs:
        best_input = usb_inputs[0]
        print(f"\n  INPUT_DEVICE_NAME={best_input[1]['name'].split(':')[0].strip()}")
    else:
        print(f"\n  INPUT_DEVICE_NAME=  # (leave blank for default)")

    # Find best output (prefer USB, then default)
    usb_outputs = [(i, info) for i, info in output_devices if "usb" in info["name"].lower()]
    if usb_outputs:
        best_output = usb_outputs[0]
        print(f"  OUTPUT_DEVICE_NAME={best_output[1]['name'].split(':')[0].strip()}")
    else:
        print(f"  OUTPUT_DEVICE_NAME=  # (leave blank for default)")

    print()


def test_input(p, device_index, duration=3):
    """Test recording from a specific device."""
    info = p.get_device_info_by_index(device_index)
    print(f"\n{'─' * 80}")
    print(f"TESTING INPUT: [{device_index}] {info['name']}")
    print(f"{'─' * 80}")

    # Find a supported sample rate
    supported_rates = check_supported_rates(p, device_index, "input")
    if not supported_rates:
        print("  ERROR: No supported sample rates found!")
        return

    # Prefer 16kHz, then 44.1kHz, then 48kHz, then whatever works
    preferred = [16000, 44100, 48000]
    test_rate = None
    for rate in preferred:
        if rate in supported_rates:
            test_rate = rate
            break
    if test_rate is None:
        test_rate = supported_rates[0]

    print(f"  Recording {duration}s at {test_rate}Hz...")
    print(f"  Speak into the microphone now!")

    chunk_size = int(test_rate * 0.03)  # 30ms frames
    frames = []

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=test_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk_size,
        )

        start = time.time()
        while time.time() - start < duration:
            data = stream.read(chunk_size, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Analyze captured audio
    audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32)
    duration_actual = len(audio) / test_rate

    print(f"\n  Results:")
    print(f"    Duration: {duration_actual:.2f}s")
    print(f"    Samples: {len(audio)}")
    print(f"    Sample rate: {test_rate}Hz")

    if len(audio) == 0:
        print("    ERROR: No audio captured!")
        return

    # RMS analysis
    rms = np.sqrt(np.mean(audio ** 2))
    peak = np.max(np.abs(audio))
    print(f"    Overall RMS: {rms:.1f}")
    print(f"    Peak amplitude: {peak:.0f} / 32768")
    print(f"    Peak dB: {20 * math.log10(peak / 32768) if peak > 0 else -100:.1f} dBFS")

    # Sliding window RMS (like the app uses)
    window_ms = 100
    window_size = int(test_rate * window_ms / 1000)
    max_rms = 0
    for i in range(0, len(audio) - window_size, window_size):
        window = audio[i:i + window_size]
        w_rms = np.sqrt(np.mean(window ** 2))
        if w_rms > max_rms:
            max_rms = w_rms

    print(f"    Peak window RMS: {max_rms:.1f} (app threshold: MIN_AUDIO_RMS, default 60)")

    if max_rms < 60:
        print(f"    ⚠  Audio is very quiet. Consider lowering MIN_AUDIO_RMS or increasing mic gain.")
    elif max_rms > 5000:
        print(f"    ⚠  Audio is very loud. Mic may be clipping.")
    else:
        print(f"    ✓  Audio levels look good for speech detection.")


def test_output(p, device_index, duration=2):
    """Test playback on a specific device with a sine wave."""
    info = p.get_device_info_by_index(device_index)
    print(f"\n{'─' * 80}")
    print(f"TESTING OUTPUT: [{device_index}] {info['name']}")
    print(f"{'─' * 80}")

    # Find a supported sample rate
    supported_rates = check_supported_rates(p, device_index, "output")
    if not supported_rates:
        print("  ERROR: No supported sample rates found!")
        return

    # Prefer 48kHz, then 44.1kHz
    preferred = [48000, 44100, 22050, 16000]
    test_rate = None
    for rate in preferred:
        if rate in supported_rates:
            test_rate = rate
            break
    if test_rate is None:
        test_rate = supported_rates[0]

    # Check stereo support
    supported_channels = check_supported_channels(p, device_index, "output")
    channels = 2 if 2 in supported_channels else 1

    print(f"  Playing {duration}s sine wave at {test_rate}Hz, {channels}ch...")
    print(f"  You should hear a tone from the speaker.")

    # Generate sine wave (440Hz A note)
    freq = 440
    samples = int(test_rate * duration)
    t = np.arange(samples) / test_rate
    tone = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)

    if channels == 2:
        stereo = np.column_stack((tone, tone))
        audio_bytes = stereo.tobytes()
    else:
        audio_bytes = tone.tobytes()

    chunk_size = 1024

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=test_rate,
            output=True,
            output_device_index=device_index,
            frames_per_buffer=chunk_size,
        )

        # Write in chunks
        offset = 0
        bytes_per_chunk = chunk_size * channels * 2  # 2 bytes per int16 sample
        while offset < len(audio_bytes):
            chunk = audio_bytes[offset:offset + bytes_per_chunk]
            stream.write(chunk)
            offset += bytes_per_chunk

        stream.stop_stream()
        stream.close()
        print(f"  ✓  Playback complete.")

    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Debug audio devices for J.F. Sebastian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/debug_audio_devices.py                  # List all devices
  python scripts/debug_audio_devices.py --test-input 24  # Test mic at index 24
  python scripts/debug_audio_devices.py --test-output 25 # Test speaker at index 25
  python scripts/debug_audio_devices.py --test-input 24 --test-output 25  # Test both
        """,
    )
    parser.add_argument(
        "--test-input",
        type=int,
        metavar="INDEX",
        help="Test recording from device at INDEX for 3 seconds",
    )
    parser.add_argument(
        "--test-output",
        type=int,
        metavar="INDEX",
        help="Test playback on device at INDEX with a sine wave",
    )
    args = parser.parse_args()

    p = pyaudio.PyAudio()

    try:
        list_devices(p)

        if args.test_input is not None:
            test_input(p, args.test_input)

        if args.test_output is not None:
            test_output(p, args.test_output)

    finally:
        p.terminate()


if __name__ == "__main__":
    main()
