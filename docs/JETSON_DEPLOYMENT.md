# Jetson Deployment Notes

These are the host-level pieces that aren't captured by `setup.sh` or any
file in the repo — system packages, GPU power tuning, PulseAudio echo
cancellation, and a few known-harmless warnings. Tested on **NVIDIA Jetson
Orin Nano Super** (8 GB unified memory) running Ubuntu 22.04 (JetPack 6.x).
Most of it also applies to the non-Super Orin Nano with one footnote on
power mode.

## Reference hardware

The configuration values throughout this document were tuned against this
specific peripheral setup. Different mic / speaker hardware will need
different gain, RMS, and threshold values, but the structure of the setup
(disabling AGC, pinning PA defaults, upgrading the resampler) carries
over.

### USB microphone

**Generic USB PnP Sound Device (C-Media chipset)** — [Amazon B0CNVZ27YH](https://www.amazon.com/dp/B0CNVZ27YH)

| | |
|---|---|
| ALSA name | `alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono` |
| USB vendor:product | `0d8c:` (C-Media Electronics) |
| Native rate | 48 kHz mono, 16-bit signed |
| Hardware AGC | Present + enabled by default (must be disabled — see Microphone tuning) |
| Connector | USB-A, plug-and-play, no driver needed on Ubuntu |
| Cost | ~$10 |

Notes: this is the kind of chipset that gets put in every cheap USB mic.
The audio quality is workable for wake-word + Whisper after the tuning
below, but it's a real downgrade from a MacBook's built-in mic with
Apple's DSP — expect to tune `MIN_AUDIO_RMS` upward (noise floor sits
around 800–1200) and to upgrade the PulseAudio resampler.

### USB speaker

**Generic AB13X USB Audio** — [Amazon B09MPL4LRD](https://www.amazon.com/dp/B09MPL4LRD)

| | |
|---|---|
| ALSA name | `alsa_output.usb-Generic_AB13X_USB_Audio_20210726905926-00.analog-stereo` |
| Native rate | 48 kHz stereo, 16-bit signed |
| Connector | USB-A, plug-and-play |
| Cost | ~$15 |

Notes: outputs at 48 kHz natively, which matches the app's 48 kHz playback
session — no playback-side resampling. Volume curve is fine; we drive at
100% via PulseAudio and let the per-device `VOICE_GAIN` overlay handle
voice loudness.

### Audio routing summary

```
   USB mic (C-Media, 48 kHz mono)
        │
        ▼
   ALSA → PulseAudio (soxr-vhq resampler) → "pulse" PortAudio device
        │
        ▼
   App: wake-word detector @ 16 kHz, recorder @ 16 kHz

   App TTS+RVC output (48 kHz stereo)
        │
        ▼
   "pulse" PortAudio device → PulseAudio → ALSA
        │
        ▼
   USB speaker (AB13X, 48 kHz stereo)
```

`INPUT_DEVICE_NAME=pulse` and `OUTPUT_DEVICE_NAME=pulse` in `.env`; the
actual hardware selection happens via PulseAudio's defaults (pinned in
`~/.config/pulse/default.pa` — see "Pin the default source and sink"
below).

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

## Microphone tuning

USB conference mics often ship with hardware Auto Gain Control enabled,
which pumps the level up between phrases and down during speech — bad
for both volume consistency and wake-word detection (the model expects
stable spectral content). Disable it via ALSA and persist:

```bash
# Find the card index for your mic
arecord -l | grep -i "your_mic_name_here"

# Disable AGC (replace 3 with your card index) and any other unwanted
# auto-processing the card exposes
amixer -c 3 set "Auto Gain Control" off

# Set capture volume to max (hardware mic gain, not PulseAudio mixer)
amixer -c 3 set "Mic Capture Volume" 100%

# Persist across reboots (alsa-restore.service reads this at boot)
sudo alsactl store
```

Also set the PulseAudio source volume to 100% so the app gets unattenuated
audio:

```bash
pactl set-source-volume alsa_input.usb-…analog-mono 100%
```

PulseAudio remembers the per-source volume across restarts via
`module-stream-restore`.

### PulseAudio resampler

The C-Media USB mic captures at 48 kHz; OpenWakeWord and Whisper both want
16 kHz, so every capture path goes through a 48 → 16 kHz resample. PA's
`auto` resampler default on Linux maps to **speex-float-1**, the cheapest
and lowest-fidelity option. On Mac the equivalent path goes through
CoreAudio's much higher-quality resampler, which is why a wake-word model
trained on Mac-captured audio scores noticeably worse when fed Jetson's
speex-float-1-resampled audio of the same speaker. Symptom: the user
reports "the wake word used to work much better on my Mac."

Fix: pin a high-quality resampler in the per-user PA config. Costs a few
percent CPU; negligible on Orin Nano. SoX-VHQ is the highest quality PA
supports.

```bash
mkdir -p ~/.config/pulse
cat > ~/.config/pulse/daemon.conf <<'EOF'
# Upgrade resampler from speex-float-1 (PA's Linux default) to soxr-vhq.
# Preserves the spectral content the wake-word model was trained against.
resample-method = soxr-vhq
EOF

# Restart PulseAudio so the new daemon.conf takes effect, then restart
# anything that was holding a stream open.
pulseaudio -k && sleep 2 && pulseaudio --start
systemctl --user restart jf-sebastian.service
```

Verify with:

```bash
pulseaudio --dump-conf | grep resample-method
# resample-method = soxr-vhq
```

Other usable options if `soxr-vhq` isn't compiled into your PA build (rare):
`speex-float-10` (close second), `soxr-hq` (slightly lighter, still much
better than the default).

### Pin the default source and sink

PulseAudio's "best device" heuristic can flip between USB mic / onboard
audio on every restart, especially if devices enumerate in different
orders. PortAudio sees PulseAudio as a single `pulse` device, so the only
way to control routing from PortAudio's side is to make the right devices
PulseAudio's defaults.

Add to `~/.config/pulse/default.pa` (create the file if needed; it
includes the system default automatically):

```
.include /etc/pulse/default.pa

# Hardcode the USB devices as the defaults — keeps the wake-word and
# recorder talking to the right hardware across reboots and replug events.
set-default-source alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono
set-default-sink   alsa_output.usb-Generic_AB13X_USB_Audio_20210726905926-00.analog-stereo
```

Replace the ALSA device names with whatever `pactl list short sources` and
`pactl list short sinks` show for your hardware.

### Echo cancellation: not needed

The app stops the PortAudio capture stream at the OS level whenever it's
about to play audio (`AudioRecorder.pause()` calls `stream.stop_stream()`,
and the wake-word detector pauses similarly). No mic input is captured
while the bot speaks, so the OS-level AEC layer that macOS provides via
CoreAudio's Voice Processing IO isn't actually doing useful work on Mac
either — it's just been benign.

If you previously enabled `module-echo-cancel` on Linux, **remove it**:
the WebRTC AEC pipeline reshapes spectral content in ways that degrade
wake-word accuracy noticeably, and any noise suppression or AGC it
applies isn't worth its cost without a self-trigger problem to solve.

```bash
# Unload the running instance
pactl unload-module module-echo-cancel

# Restore raw devices as defaults (no virtual sources in the path)
pactl set-default-source alsa_input.usb-…analog-mono
pactl set-default-sink   alsa_output.usb-…analog-stereo
```

And remove or comment out the `load-module module-echo-cancel …` block
from `~/.config/pulse/default.pa` so it doesn't come back at next start.

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

## Audio settings reference

Everything that affects audio capture or playback, in one place. The
defaults in `.env.example` are tuned for a quiet room and a MacBook mic;
the values below are what worked on the Jetson + C-Media USB mic + AB13X
USB speaker. Adjust to your room.

### Input (capture) settings

| Setting | Jetson value | Default | What it does |
|---|---|---|---|
| `INPUT_DEVICE_NAME` | `pulse` | `pulse` | PortAudio device name. `pulse` routes through PulseAudio's default source — set the default via `~/.config/pulse/default.pa`. |
| `SAMPLE_RATE` | `16000` | `16000` | Capture sample rate fed to wake-word + Whisper. **Must be 16000** — Silero VAD requires it, OpenWakeWord requires it. PA resamples from the mic's native 48 kHz. |
| `MIN_AUDIO_RMS` | `1000`–`1600` | `60` | Stage-2 silence filter. C-Media USB mics have a noise floor around 800–1200; the default 60 lets all of that pass to Whisper which then hallucinates ("Thanks for watching!"). Tune upward until ambient room passes through silently. |
| `MIN_SPEECH_RATIO` | `0.2` | `0.3` | Stage-3 Silero VAD threshold — % of audio frames that must be classified as speech. With Silero VAD (vs the old WebRTC VAD) this can be lower than the historical default. |
| `VAD_THRESHOLD` | `0.5`–`0.6` | `0.5` | Per-window Silero speech-probability cutoff. Higher = stricter. Raise toward 0.7 if noise still leaks through; lower toward 0.3 if real speech is rejected. |
| `SPEECH_END_SILENCE_SECONDS` | `2.0` | `1.0` | How long of silence ends user speech. Bump up if you tend to pause mid-question. |
| `MIN_LISTEN_SECONDS` | `2.0` | `1.0` | Min recording window after wake-word fires (prevents premature cutoff on the "Hey José... [pause] ...what time is it" pattern). |
| `WAKE_WORD_THRESHOLD` | `0.93` | `0.99` | OpenWakeWord confidence cutoff. 0.99 is very strict (default). 0.93 catches some borderline utterances; going below ~0.85 starts catching not-wake-word audio (false fires on TV/conversation). |
| `SILENCE_TIMEOUT` | `5.0` | `10.0` | Max recording duration regardless of speech. Forces a return to IDLE on stuck-open recordings. |

### Output (playback) settings

| Setting | Jetson value | Default | What it does |
|---|---|---|---|
| `OUTPUT_DEVICE_NAME` | `pulse` | `pulse` | PortAudio device name for playback. Pin via PulseAudio default sink. |
| `OUTPUT_DEVICE_TYPE` | `squawkers_mccaw` | `teddy_ruxpin` | Selects the audio-processing pipeline. Headless = simple stereo; Teddy = stereo with PPM control track in the right channel; Squawkers = simple stereo for the Squawkers McCaw animatronic. |
| `VOICE_GAIN` | `1.05`–`1.8` | `1.05` | Voice volume multiplier applied to both RVC-converted and raw TTS paths. Bump up for quiet RVC models; clip to 2.0 max. |
| `CONTROL_GAIN` | `0.52` | `0.52` | PPM control-track amplitude (Teddy only). Affects motor strength. |
| `PLAYBACK_PREROLL_MS` | `240` | `240` | Silence before playback starts, to avoid clipping the first syllable while the audio device warms up. |
| `PLAYBACK_TAIL_GUARD_MS` | `500` | `500` | Silence after playback ends before reopening the mic. Covers speaker buffer drain and acoustic decay so the bot doesn't self-trigger on its own tail audio. Raise if the bot still triggers on itself. |

### Per-device overrides

If a setting needs to differ between output devices (e.g. `VOICE_GAIN`
needs to be louder on the Squawkers' speaker than on the Teddy's), put it
in `jf_sebastian/devices/{OUTPUT_DEVICE_TYPE}/.env`:

```
# jf_sebastian/devices/squawkers_mccaw/.env
VOICE_GAIN=1.8
```

Personality-specific overrides go in `personalities/{name}/.env` and
beat the device-level ones. See the README for the full precedence order.

### Code-level defaults worth knowing

These aren't `.env` settings but are values baked into the audio path that
affect Jetson-class hardware specifically:

| Where | Value | Why |
|---|---|---|
| `audio_output.py` output stream `frames_per_buffer` | 4096 | ~85 ms of buffer headroom. The PyAudio default (1024 ≈ 21 ms) was too tight on Jetson and triggered `snd_pcm_recover` underruns whenever the playback worker stalled briefly. |
| `audio_input.py` capture stream | Silero's required 512-sample windows | Locked to 16 kHz / 512-sample chunks for Silero VAD frame alignment. |
| `wake_word.py` chunk size | 1280 samples (80 ms at 16 kHz) | OpenWakeWord's required input granularity. |
