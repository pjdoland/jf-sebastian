# Jetson Deployment Notes

These are the host-level pieces that aren't captured by `setup.sh` or any
file in the repo — system packages, GPU power tuning, PulseAudio echo
cancellation, and a few known-harmless warnings. Tested on **NVIDIA Jetson
Orin Nano Super** (8 GB unified memory) running Ubuntu 22.04 (JetPack 6.x).
Most of it also applies to the non-Super Orin Nano with one footnote on
power mode.

## System packages

`setup.sh` installs Python deps but not the OS libraries those deps link
against. Install these first:

```bash
sudo apt update
sudo apt install -y \
    python3.10-venv \
    portaudio19-dev libportaudio2 libasound2-dev \
    ffmpeg
```

Why each one matters:

- `python3.10-venv` — `python3 -m venv` fails to bootstrap pip without it.
- `portaudio19-dev` — PyAudio compiles from source on aarch64 (no wheel)
  and needs `portaudio.h`. Without it, `pip install pyaudio` errors mid-setup.
- `libportaudio2` — runtime shared library PyAudio links against.
- `libasound2-dev` — ALSA dev headers required by PyAudio's Linux backend.
- `ffmpeg` — used by the audio processor for MP3 → PCM conversion of
  OpenAI TTS output.

## GPU power tuning

The Orin Nano Super ships throttled by default. For sustained RVC
throughput you want the highest power profile plus locked clocks.

### List available power profiles

```bash
sudo nvpmodel -q
grep "POWER_MODEL" /etc/nvpmodel.conf
```

On the **Super** developer kit the modes are:

| ID | Name         | Notes                                       |
|----|--------------|---------------------------------------------|
| 0  | 15W          | Standard Orin Nano max                      |
| 1  | 25W          | —                                           |
| 2  | `MAXN_SUPER` | **The Super-only unlocked profile**         |
| 3  | 7W           | Low-power                                   |

On the **non-Super** Orin Nano, mode 0 (`MAXN`) is the highest available
profile — there is no `MAXN_SUPER`.

### Apply the profile

```bash
sudo nvpmodel -m 2          # MAXN_SUPER (use -m 0 on non-Super)
sudo jetson_clocks          # lock CPU/GPU/EMC to the profile's ceiling
```

`nvpmodel` persists across reboots automatically. `jetson_clocks` does
**not** — see the next section for the systemd unit that re-applies it
at boot.

### Verify

```bash
sudo nvpmodel -q             # should print "MAXN_SUPER" (or your choice)
sudo jetson_clocks --show    # CPU/GPU/EMC MaxFreq == CurrentFreq
```

### Persist `jetson_clocks` across reboots

Install a one-shot systemd unit that runs after `nvpmodel.service`:

```bash
sudo tee /etc/systemd/system/jetson-clocks.service > /dev/null <<'EOF'
[Unit]
Description=Lock Jetson CPU/GPU/EMC clocks to the current nvpmodel ceiling
After=nvpmodel.service
Requires=nvpmodel.service

[Service]
Type=oneshot
ExecStart=/usr/bin/jetson_clocks
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now jetson-clocks.service
```

The `After=nvpmodel.service` ordering matters — locking clocks before the
power profile is applied would clamp them to whatever profile was active
during boot rather than the persistent one.

To undo: `sudo systemctl disable --now jetson-clocks.service`.

## Acoustic Echo Cancellation (AEC)

macOS gives you AEC for free via CoreAudio's Voice Processing IO unit;
Linux does not. Without AEC, the microphone picks up the bot's own
playback and the system can trigger on itself (mostly during the
"continue conversation" listen window — wake-word self-trigger is
already prevented in code).

The Jetson runs PulseAudio by default. Load `module-echo-cancel` (which
uses WebRTC's AEC — the same algorithm Chrome / Google Meet uses) and
make the virtual devices PulseAudio's defaults so PortAudio routes
through them transparently.

Create `~/.config/pulse/default.pa`:

```
#!/usr/bin/pulseaudio -nF
# Loaded INSTEAD of /etc/pulse/default.pa, so we include the system
# defaults first and then add our own.

.include /etc/pulse/default.pa

# WebRTC AEC binding the USB mic to the USB speaker. Adjust the
# source_master / sink_master values to match your hardware — get the
# exact ALSA names from `pactl list short sources` / `… short sinks`.
load-module module-echo-cancel \
    aec_method=webrtc \
    source_master=alsa_input.usb-…analog-mono \
    sink_master=alsa_output.usb-…analog-stereo \
    source_name=echocancel \
    sink_name=echocancel-sink \
    source_properties=device.description=EchoCancelMic \
    sink_properties=device.description=EchoCancelSpeaker

# PyAudio/PortAudio only sees PulseAudio as a single "pulse" device, so
# the only way to route through the AEC is to make the virtual devices
# the PulseAudio defaults.
set-default-source echocancel
set-default-sink echocancel-sink
```

Then point the app at the generic `pulse` device in `.env`:

```
INPUT_DEVICE_NAME=pulse
OUTPUT_DEVICE_NAME=pulse
```

Reload PulseAudio (`pulseaudio -k` — autospawn restarts it) and verify
the app's source-output and sink-input show source 7 (`echocancel`) and
sink 4 (`echocancel-sink`) while it's running:

```bash
pactl list source-outputs | grep -E "Source:|application.name"
pactl list sink-inputs    | grep -E "Sink:|application.name"
```

If you want to crank the suppression further, add to the load-module
line:

```
aec_args="analog_gain_control=0 digital_gain_control=1 noise_suppression=1 high_pass_filter=1"
```

## PyTorch CUDA allocator tuning

Long RVC sessions can fragment the CUDA caching allocator on Jetson and
trigger `NVML_SUCCESS == r INTERNAL ASSERT FAILED at
CUDACachingAllocator.cpp:1131` errors. The setting that fixes it is
already exported by `run.sh` and both supervisor unit templates:

```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

(Harmless on Mac — PyTorch silently ignores it when CUDA isn't
available.) If you're starting Python any other way, set this before
the Python process starts. The `rvc_processor.py` module also calls
`torch.cuda.empty_cache()` after each conversion as cheap insurance.

## Known harmless warnings

`onnxruntime` (used by OpenWakeWord) emits this on every start:

```
[W:onnxruntime:Default, device_discovery.cc:164 DiscoverDevicesForPlatform]
GPU device discovery failed: device_discovery.cc:89 ReadFileContents
Failed to open file: "/sys/class/drm/card1/device/vendor"
```

It's enumerating discrete PCIe GPUs the standard Linux way; the Jetson's
integrated Tegra GPU doesn't expose itself through `/sys/class/drm`. The
PyPI `onnxruntime` wheel is CPU-only anyway, and OpenWakeWord doesn't
need a GPU — its ONNX model is tiny and runs in microseconds on CPU.
Ignore the line.

## RVC install on Jetson

`setup.sh` detects the Jetson and routes RVC install through the [Jetson
AI Lab wheel index](https://pypi.jetson-ai-lab.io/) so that
PyTorch/torchaudio land with CUDA support. It pins `torch==2.8.0` —
newer torch wheels (≥ 2.9) require `libcudss` which JetPack 6.1 doesn't
ship. Remaining RVC deps come from `requirements-rvc-jetson.txt`.

If you skipped RVC at first-run setup and want to add it later:

```bash
./scripts/install_rvc.sh
```

The compile of `praat-parselmouth` (a transitive dep) takes 20–40 min
from source on aarch64 — there's no prebuilt wheel and it bundles the
entire Praat C++ codebase. This is normal; let it cook.
