# J.F. Sebastian

> *"I make friends. They're toys. My friends are toys. I make them. It's a hobby."*
> — J.F. Sebastian, Blade Runner

An AI conversation system that brings life to vintage animatronic toys. Built with a modular device architecture, this system supports multiple output devices including the 1985 Teddy Ruxpin and Squawkers McCaw. Features real-time voice conversations with ChatGPT, a modular personality system with unique wake words, voices, and conversational styles.

Includes six distinct personalities: a tiki bartender, Abraham Lincoln (a homage to Disney's pioneering animatronics), an eccentric conspiracy theorist, Mister Rogers, K.I.T.T. from Knight Rider, and the classic Teddy Ruxpin character. Add your own personalities using simple YAML files - no programming required!

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


<!-- TOC -->

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [System Requirements](#system-requirements)
  - [Software](#software)
  - [Hardware](#hardware)
- [Hardware Setup](#hardware-setup)
  - [Teddy Ruxpin Connection](#teddy-ruxpin-connection)
    - [Recommended Bluetooth Adapter](#recommended-bluetooth-adapter)
    - [Setup Steps](#setup-steps)
- [Installation](#installation)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Create Virtual Environment](#2-create-virtual-environment)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Download OpenWakeWord Preprocessing Models](#4-download-openwakeword-preprocessing-models)
  - [5. Install System Dependencies](#5-install-system-dependencies)
  - [6. Configuration](#6-configuration)
  - [7. Get API Keys](#7-get-api-keys)
    - [OpenAI API Key](#openai-api-key)
    - [Wake Word Models (OpenWakeWord)](#wake-word-models-openwakeword)
  - [8. Finding Audio Devices](#8-finding-audio-devices)
  - [9. Generate Filler Audio](#9-generate-filler-audio)
- [Personalities](#personalities)
  - [Available Personalities](#available-personalities)
    - [Johnny - Tiki Bartender](#johnny-tiki-bartender)
    - [Mr. Lincoln - Abraham Lincoln](#mr-lincoln-abraham-lincoln)
    - [Leopold - Conspiracy Theorist](#leopold-conspiracy-theorist)
  - [Switching Personalities](#switching-personalities)
  - [Generating Filler Audio](#generating-filler-audio)
- [Usage](#usage)
  - [Starting the Application](#starting-the-application)
  - [Having a Conversation](#having-a-conversation)
  - [Conversation Examples](#conversation-examples)
- [Configuration Options](#configuration-options)
  - [.env Settings](#env-settings)
    - [Personality & API Configuration](#personality-api-configuration)
    - [Audio Device Configuration](#audio-device-configuration)
    - [Voice Activity Detection](#voice-activity-detection)
    - [Conversation Settings](#conversation-settings)
    - [OpenAI Models](#openai-models)
    - [Animatronic Control](#animatronic-control)
    - [Debug Settings](#debug-settings)
    - [Deprecated Settings](#deprecated-settings)
  - [Creating Custom Personalities](#creating-custom-personalities)
- [Architecture](#architecture)
  - [Key Components](#key-components)
- [Troubleshooting](#troubleshooting)
  - [Wake Word Not Detecting](#wake-word-not-detecting)
  - [Audio Device Issues](#audio-device-issues)
  - [API Errors](#api-errors)
  - [Teddy Not Moving](#teddy-not-moving)
  - [Latency Issues](#latency-issues)
- [Debug Mode](#debug-mode)
- [Development](#development)
  - [Project Structure](#project-structure)
  - [Running Tests](#running-tests)
  - [Adding Features](#adding-features)
- [Performance Metrics](#performance-metrics)
- [Cost Estimates](#cost-estimates)
- [About the Name](#about-the-name)
- [License](#license)
- [Credits](#credits)
- [Contributing](#contributing)
- [Support](#support)

<!-- /TOC -->

## Features

- **Modular Device Architecture**: Supports multiple output devices with simple configuration
  - **Teddy Ruxpin**: Full animatronic control with PPM signals for mouth and eyes
  - **Squawkers McCaw**: Simple stereo audio output without PPM
  - Easy to extend for additional devices
- **Modular Personality System**: Switch between different AI personalities with unique voices and behaviors
  - **Johnny**: Tiki bartender with deep knowledge of tiki culture ("Hey, Johnny")
  - **Mr. Lincoln**: Abraham Lincoln, 16th President - homage to Disney's animatronics ("Hey, Mr. Lincoln")
  - **Leopold**: Eccentric conspiracy theorist with a wild backstory ("Hey, Leopold")
  - **Fred**: Mister Rogers with gentle warmth and simple wisdom ("Hey, Fred")
  - **K.I.T.T.**: Knight Industries Two Thousand AI from Knight Rider ("Hey, Kitt")
  - **Teddy Ruxpin**: The classic storytelling bear from Grundo ("Hey, Teddy Ruxpin")
- **Wake Word Activation**: Custom wake words per personality using OpenWakeWord (free & open source)
- **Low-Latency Fillers**: Pre-generated personality-specific phrases play immediately while processing
- **Speech Recognition**: OpenAI Whisper API for accurate speech-to-text transcription
- **AI Conversation**: GPT-4o-mini powers personality-driven responses with conversation context
- **Streaming Response Pipeline**: Word-based sentence chunking enables parallel TTS/RVC processing while LLM generates
- **Natural Voice**: OpenAI TTS (gpt-4o-mini-tts) generates speech with personality-specific voices, speeds, and tones
- **RVC Voice Conversion** (Optional): Transform TTS output with custom trained voice models for unique character voices beyond OpenAI TTS
- **Animatronic Control** (Teddy Ruxpin): Generates PPM control signals for mouth (syllable-based lip sync) and eyes (sentiment-based)
- **Flexible Output**: Device-specific audio processing (stereo with PPM for Teddy, simple stereo for Squawkers)

## Quick Start

**New to J.F. Sebastian?** See the [Quick Start Guide](docs/QUICKSTART.md) to get your animatronic talking in 5 minutes!

## System Requirements

### Software
- Python 3.10.x (specifically - RVC dependencies are not compatible with 3.11+)
- macOS (currently configured for Mac audio devices)
- Internet connection for OpenAI APIs

### Hardware
- **Supported Devices**:
  - **1985 Teddy Ruxpin doll** (cassette-based model) - full animatronic control
  - **Squawkers McCaw** - simple audio output
  - Other animatronics can be added via the modular device architecture
- **Bluetooth cassette adapter** (for Teddy Ruxpin, recommended: [Arsvita Car Audio Bluetooth Wireless Cassette Receiver](https://www.amazon.com/dp/B085C7GTBD))
- Microphone for voice input

## Hardware Setup

### Teddy Ruxpin Connection

This system is designed to work with an original **1985 cassette-based Teddy Ruxpin doll**. The cassette mechanism provides both audio playback and motor control through a stereo audio signal.

#### Recommended Bluetooth Adapter

**[Arsvita Car Audio Bluetooth Wireless Cassette Receiver](https://www.amazon.com/dp/B085C7GTBD)**
- Designed for car cassette players but works perfectly with Teddy Ruxpin
- Reliable Bluetooth 5.0 connection
- Good audio quality for both voice and control signals
- Rechargeable battery (charges via USB-C)

#### Setup Steps

1. **Insert Bluetooth Cassette Adapter**: Place the adapter into Teddy's cassette deck
2. **Audio Routing**:
   - LEFT channel → Teddy's speaker (voice)
   - RIGHT channel → Control track (mouth/eye motors)
3. **Pairing**: Pair the Bluetooth adapter with your Mac
4. **Device Selection**: Note the device name (see Configuration section)

## Installation

You can install J.F. Sebastian using either the automated setup script (recommended) or manual step-by-step installation.

### Method 1: Automated Installation (Recommended)

The easiest way to get started is using the provided setup script:

```bash
# Clone the repository
git clone https://github.com/pjdoland/jf-sebastian.git
cd jf-sebastian

# Run automated setup
./setup.sh
```

The setup script will automatically:
1. Check Python version (3.10.x specifically - required for RVC compatibility)
2. Create virtual environment with Python 3.10
3. Upgrade pip to latest version
4. Install Python dependencies from requirements.txt
5. Optionally install RVC voice conversion dependencies (asks for confirmation)
6. Download OpenWakeWord preprocessing models
7. Install system dependencies (PortAudio, FFmpeg via Homebrew)
8. Create required directories
9. Create `.env` configuration file from template
10. List available audio devices
11. Optionally generate filler audio for all personalities (asks for confirmation)
12. Check for wake word models

**After running setup.sh:**
1. Edit `.env` and add your OpenAI API key:
   ```bash
   OPENAI_API_KEY=sk-your-openai-api-key
   ```
2. Configure audio devices in `.env` (see device list from setup):
   ```bash
   INPUT_DEVICE_NAME=MacBook Air Microphone
   OUTPUT_DEVICE_NAME=Arsvita
   ```
3. You're ready to run: `./run.sh`

### Method 2: Manual Installation

If you prefer more control or need to troubleshoot, you can install manually:

#### 1. Clone the Repository

```bash
git clone https://github.com/pjdoland/jf-sebastian.git
cd jf-sebastian
```

#### 2. Create Virtual Environment

**Important:** RVC voice conversion requires Python 3.10.x specifically (not 3.11+). If you plan to use RVC, ensure you're using Python 3.10:

```bash
# Check your Python version
python3 --version  # Should show 3.10.x

# If you need Python 3.10, install via:
# - pyenv: pyenv install 3.10.13 && pyenv local 3.10.13
# - Homebrew: brew install python@3.10 (then use python3.10 command)

# Create virtual environment with Python 3.10
python3 -m venv venv
# Or if using python3.10 from Homebrew:
# python3.10 -m venv venv

source venv/bin/activate  # On macOS/Linux
```

#### 3. Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt
```

#### 4. Download OpenWakeWord Preprocessing Models

OpenWakeWord requires preprocessing models that must be downloaded separately:

```bash
python3 -c "from openwakeword import utils; utils.download_models(['alexa'])"
```

This downloads the required `melspectrogram.onnx` and `embedding_model.onnx` files to the openwakeword package directory.

#### 5. Install System Dependencies

For audio processing, you may need additional system libraries:

```bash
# macOS
brew install portaudio ffmpeg

# The application uses:
# - PortAudio (for PyAudio)
# - FFmpeg (for MP3 to PCM conversion)
```

#### 6. Configuration

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```bash
# Personality Selection
PERSONALITY=johnny  # Options: 'johnny', 'mr_lincoln', 'leopold', 'fred', 'kitt', 'teddy_ruxpin'

# Required API Keys
OPENAI_API_KEY=sk-your-openai-api-key

# Audio device names (see "Finding Audio Devices" below)
INPUT_DEVICE_NAME=MacBook Air Microphone
OUTPUT_DEVICE_NAME=Arsvita
```

#### 7. Get API Keys

**OpenAI API Key:**
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to `.env` as `OPENAI_API_KEY`

**Wake Word Models (OpenWakeWord):**

No API key required! OpenWakeWord is completely free and open source.

Each personality includes its own wake word model file:
- Johnny: `personalities/johnny/hey_johnny.onnx`
- Mr. Lincoln: `personalities/mr_lincoln/hey_mr_lincoln.onnx`
- Leopold: `personalities/leopold/hey_leopold.onnx`
- Fred: `personalities/fred/hey_fred.onnx`
- K.I.T.T.: `personalities/kitt/hey_kitt.onnx`
- Teddy Ruxpin: `personalities/teddy_ruxpin/hey_teddy_ruxpin.onnx`

To create a custom wake word for a new personality:
1. Follow the guide in `docs/TRAIN_WAKE_WORDS.md`
2. Train a model for your desired wake phrase
3. Place the `.onnx` model file in your personality's directory

#### 8. Finding Audio Devices

Run the audio output utility to list all devices:

```bash
python -m jf_sebastian.modules.audio_output
```

This will display:
```
Available Audio Devices:
--------------------------------------------------------------------------------
[0] MacBook Pro Microphone
    Type: INPUT
    Channels: In=1, Out=0
    Sample Rate: 48000.0 Hz

[1] MacBook Pro Speakers
    Type: OUTPUT
    Channels: In=0, Out=2
    Sample Rate: 48000.0 Hz

[2] Bluetooth Cassette Adapter
    Type: OUTPUT
    Channels: In=0, Out=2
    Sample Rate: 44100.0 Hz
```

Update `.env` with the appropriate device names:
```bash
INPUT_DEVICE_NAME=MacBook Air Microphone
OUTPUT_DEVICE_NAME=Arsvita
```

#### 9. Optional: Install RVC for Custom Voice Models

**RVC (Retrieval-based Voice Conversion) is optional.** The system works perfectly with OpenAI TTS voices alone. Install RVC only if you want to use custom trained voice models for unique character voices.

**Requirements:**
- Python 3.10.x specifically (RVC is not compatible with Python 3.11+)
- Requires temporarily downgrading pip for compatibility

**Installation:**

```bash
# Method 1: Use the automated script (recommended)
./scripts/install_rvc.sh

# Method 2: Manual installation
# Step 1: Downgrade pip for RVC compatibility
pip install pip==24.0

# Step 2: Install RVC dependencies
pip install -r requirements-rvc.txt

# Step 3: Upgrade pip back to latest
pip install --upgrade pip
```

The `requirements-rvc.txt` file includes: torch, torchaudio, fairseq, librosa, and rvc-python.

**Troubleshooting RVC Installation:**
- If you get dependency conflicts, try: `pip install rvc-python --no-deps` then install dependencies manually
- For Apple Silicon (M1/M2/M3): Ensure you have the MPS-enabled torch version
- For CUDA: Install CUDA-enabled torch first: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118`

**To skip RVC:** The system will automatically detect RVC availability and work without it.

See [docs/CREATING_PERSONALITIES.md](docs/CREATING_PERSONALITIES.md#advanced-rvc-voice-conversion) for RVC configuration and usage.

#### 10. Generate Filler Audio (Optional but Recommended)

**Filler phrases** are pre-recorded audio clips that play immediately when you speak, creating a natural conversational feel while the system processes your question in the background. The system can work without them, but conversations will feel more responsive with filler audio.

Generate the filler audio for all personalities:

```bash
python scripts/generate_fillers.py
```

This creates device-specific filler audio for each registered output device. For each personality, it generates:
- `filler_audio/teddy_ruxpin/` - Filler audio with PPM control signals for mouth and eyes
- `filler_audio/squawkers_mccaw/` - Filler audio with simple stereo (no PPM)

Each device-specific directory contains 30 WAV files with:
- Voice audio synthesized with the personality's configured voice, speed, and tone
- Device-appropriate audio processing (PPM signals for Teddy Ruxpin, simple stereo for Squawkers McCaw)

**Note:** The filler audio files are generated per output device type, so each personality will have device-specific versions automatically created based on the registered output devices.

**When to regenerate filler audio:**
- After creating a new personality
- After switching to a different personality (if fillers don't exist yet for your output device)
- After modifying a personality's `tts_voice`, `tts_speed`, or `tts_style` settings
- After editing the `filler_phrases` list in the personality YAML file
- After adding support for a new output device type

**Personality-specific generation:**
By default, the script generates fillers for **all** personalities. To generate for just one personality:
```bash
python scripts/generate_fillers.py --personality johnny
```

**Device-specific storage:**
Each personality stores filler audio in device-specific subdirectories:
```
personalities/johnny/filler_audio/
├── teddy_ruxpin/       # 30 WAV files with PPM control signals
│   ├── filler_01.wav
│   └── ...
└── squawkers_mccaw/    # 30 WAV files with simple stereo
    ├── filler_01.wav
    └── ...
```

## Personalities

The system includes a modular personality framework. Each personality has:
- Unique **wake word** for activation
- Custom **system prompt** defining character and knowledge
- Specific **TTS voice** from OpenAI
- **Filler phrases** that play immediately for low-latency feel
- Pre-generated **filler audio** files with motor control signals

### Available Personalities

#### Johnny - Tiki Bartender
- **Wake word**: "Hey, Johnny"
- **Voice**: Onyx (casual male)
- **Character**: Laid-back beatnik bartender with deep tiki culture knowledge
- **Topics**: Cocktails, surf music, Polynesian pop, tiki history

#### Mr. Lincoln - Abraham Lincoln
- **Wake word**: "Hey, Mr. Lincoln"
- **Voice**: Echo (dignified male)
- **Character**: 16th President of the United States - a homage to Disney's Great Moments with Mr. Lincoln
- **Topics**: Liberty, equality, union, Constitution, leadership, moral conviction

#### Leopold - Conspiracy Theorist
- **Wake word**: "Hey, Leopold"
- **Voice**: Onyx (conspiratorial)
- **Character**: Eccentric truth-seeker with an insane backstory (Turkish prison, UFO abductions, intelligence work)
- **Topics**: Conspiracies, surveillance, government secrets, paranoid theories

#### Fred - Mister Rogers
- **Wake word**: "Hey, Fred"
- **Voice**: Echo with RVC (gentle, warm)
- **Character**: Fred Rogers from Mister Rogers' Neighborhood - speaks with gentle warmth and simple wisdom
- **Topics**: Feelings, kindness, being special just as you are, taking time, the neighborhood

#### K.I.T.T. - Knight Industries Two Thousand
- **Wake word**: "Hey, Kitt"
- **Voice**: Onyx with RVC (sophisticated AI)
- **Character**: Advanced AI from the Knight Rider Trans Am - intelligent with dry wit
- **Topics**: Advanced technology, crime fighting, surveillance mode, turbo boost, molecular bonded shell

#### Teddy Ruxpin - Storytelling Bear
- **Wake word**: "Hey, Teddy Ruxpin"
- **Voice**: Echo with RVC (friendly, enthusiastic)
- **Character**: Adventurous teddy bear from the magical land of Grundo
- **Topics**: Adventures, friendship, Grubby, ancient treasures, magical crystals, storytelling

### Switching Personalities

Edit `.env` to change personalities:

```bash
# Switch to Johnny (Tiki Bartender)
PERSONALITY=johnny

# Switch to Mr. Lincoln (Abraham Lincoln)
PERSONALITY=mr_lincoln

# Switch to Leopold (Conspiracy Theorist)
PERSONALITY=leopold

# Switch to Fred (Mister Rogers)
PERSONALITY=fred

# Switch to K.I.T.T. (Knight Rider AI)
PERSONALITY=kitt

# Switch to Teddy Ruxpin (Storytelling Bear)
PERSONALITY=teddy_ruxpin
```

**Important:** After switching personalities, regenerate the filler audio if it doesn't exist yet:

```bash
python scripts/generate_fillers.py
```

See `personalities/README.md` for detailed instructions on creating new personalities.

Personalities are simple YAML files - no coding required! Just copy an existing personality folder and modify the `personality.yaml` file.

## Usage

### Starting the Application

```bash
python -m jf_sebastian.main
```

You should see (example with Johnny personality):
```
================================================================================
J.F. Sebastian - Animatronic AI Conversation System
"I make friends. They're toys. My friends are toys."
================================================================================
Personality: Johnny
Wake word: Hey Johnny
...
System ready! Say 'Hey, Johnny' to start talking.
Press Ctrl+C to exit.
================================================================================
```

### Having a Conversation

1. **Wake the character**: Say the wake word ("Hey, Johnny", "Hey, Mr. Lincoln", "Hey, Leopold", "Hey, Fred", "Hey, Kitt", or "Hey, Teddy Ruxpin")
2. **Speak**: Once detected, speak your message
3. **Listen**: Character responds with personality-appropriate answer
4. **Repeat**: Continue the conversation

The system will:
- Listen for your speech
- Auto-detect when you stop talking
- Play a filler phrase immediately (0.5-second natural pause)
- Process in background: transcribe, generate response, synthesize speech
- Seamlessly transition from filler to real response
- Animate mouth and eyes during speech

### Conversation Examples

**With Johnny (Tiki Bartender):**
```
You: "Hey, Johnny"
Johnny: [Acknowledges]

You: "What's your favorite rum?"
Johnny: "Hold on, I'm checking the rum barrel... Alright, so I gotta say, a good aged Jamaican rum is hard to beat. The funk and complexity are just incredible in a Mai Tai."

You: "Tell me about tiki culture"
Johnny: "Just grabbing some fresh mint... So tiki culture started in the 1930s with Don the Beachcomber and Trader Vic. They created this whole Polynesian fantasy..."
```

**With Mr. Lincoln (Abraham Lincoln):**
```
You: "Hey, Mr. Lincoln"
Mr. Lincoln: [Acknowledges]

You: "What does freedom mean to you?"
Mr. Lincoln: "Let me consult my notes on this... Freedom is not the liberty to do as you please, but the opportunity to do what is right. True liberty requires both law and moral conviction."

You: "How did you handle the pressure of the Civil War?"
Mr. Lincoln: "Reviewing my correspondence from that time... The burden was immense, but I was guided by one principle - preserving the Union and ending slavery. When the cause is just, you endure."
```

**With Leopold (Conspiracy Theorist):**
```
You: "Hey, Leopold"
Leopold: [Acknowledges]

You: "What do you think about surveillance?"
Leopold: "Hold on, checking my bug detector... Okay, we're clean. Listen, they're watching everything. I've found three devices in my apartment last month. The surveillance is real, and it's everywhere."

You: "Have you really been abducted by aliens?"
Leopold: "Just reviewing my notes from the second abduction... Twice, actually. 1997. The first time was definitely more invasive. After they installed the implant, communication improved. You probably think I'm crazy, but the evidence is all there."
```

## Configuration Options

### .env Settings

#### Personality & API Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `PERSONALITY` | Active personality ('johnny', 'mr_lincoln', 'leopold', 'fred', 'kitt', 'teddy_ruxpin') | johnny |
| `OPENAI_API_KEY` | OpenAI API key (required) | - |

#### Audio Device Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `INPUT_DEVICE_NAME` | Microphone device name | - |
| `OUTPUT_DEVICE_NAME` | Speaker device name | - |
| `OUTPUT_DEVICE_TYPE` | Output device type ('teddy_ruxpin', 'squawkers_mccaw') | teddy_ruxpin |
| `SAMPLE_RATE` | Audio sample rate (Hz) - must be 16000, 22050, 44100, or 48000 | 16000 |
| `CHUNK_SIZE` | Audio chunk size for processing | 1024 |

#### Voice Activity Detection

| Setting | Description | Default |
|---------|-------------|---------|
| `VAD_AGGRESSIVENESS` | Voice activity detection aggressiveness (0-3, higher = more aggressive) | 3 |
| `SILENCE_TIMEOUT` | Max silence before timeout (seconds) | 5.0 |
| `SPEECH_END_SILENCE_SECONDS` | Silence required to end speech after talking (seconds) | 0.5 |
| `MIN_LISTEN_SECONDS` | Minimum listen window after wake word (seconds) | 1.0 |

#### Conversation Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `CONVERSATION_TIMEOUT` | Clear history after idle (seconds) | 120.0 |
| `MAX_HISTORY_LENGTH` | Maximum conversation history messages to maintain | 20 |
| `MIN_CHUNK_WORDS` | Minimum word count per streaming chunk (word-based sentence chunking) | 15 |
| `MAX_TOKENS` | Maximum tokens for non-streaming GPT responses | 300 |
| `MAX_TOKENS_STREAMING` | Maximum tokens for streaming GPT responses | 200 |

#### OpenAI Models

| Setting | Description | Default |
|---------|-------------|---------|
| `WHISPER_MODEL` | OpenAI Whisper speech-to-text model | whisper-1 |
| `GPT_MODEL` | OpenAI GPT model for conversation | gpt-4o-mini |
| `TTS_MODEL` | OpenAI text-to-speech model | gpt-4o-mini-tts |

**Note**: TTS voice, speed, and style are defined per personality in `personalities/` (not in .env). The gpt-4o-mini-tts model supports prompting for tone, emotional range, intonation, and speaking style.

#### Animatronic Control

| Setting | Description | Default |
|---------|-------------|---------|
| `PLAYBACK_PREROLL_MS` | Audio playback preroll (milliseconds) to prevent clipped starts | 240 |
| `VOICE_GAIN` | Voice audio volume level (0.0 to 2.0) | 1.05 |
| `CONTROL_GAIN` | Control track volume level (0.0 to 1.0) | 0.52 |
| `SENTIMENT_POSITIVE_THRESHOLD` | Sentiment threshold for positive eye expressions | 0.3 |
| `SENTIMENT_NEGATIVE_THRESHOLD` | Sentiment threshold for negative eye expressions | -0.3 |

#### Wake Word Detection

| Setting | Description | Default |
|---------|-------------|---------|
| `WAKE_WORD_THRESHOLD` | Wake word detection threshold (0.0 to 1.0, higher = more strict) | 0.99 |

#### RVC (Voice Conversion) Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `RVC_ENABLED` | Global enable/disable for RVC voice conversion | true |
| `RVC_DEVICE` | Device for RVC inference (cpu/mps/cuda) - mps for Apple Silicon GPU | mps |

**Note**: RVC is configured per-personality in `personality.yaml`. See [docs/CREATING_PERSONALITIES.md](docs/CREATING_PERSONALITIES.md) for RVC setup details. When enabled, RVC transforms TTS output to create unique character voices that go beyond what OpenAI TTS can provide alone.

#### Debug Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `DEBUG_MODE` | Enable debug features | false |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `SAVE_DEBUG_AUDIO` | Save audio files for debugging | false |
| `DEBUG_AUDIO_PATH` | Directory for debug audio files | ./debug_audio/ |


### Creating Custom Personalities

Creating a new personality is easy - just create a folder and a YAML file!

**📖 Full Guide:** See [docs/CREATING_PERSONALITIES.md](docs/CREATING_PERSONALITIES.md) for a comprehensive step-by-step guide.

**Quick Reference:** See `personalities/README.md` for technical details.

Each personality is defined in a simple `personality.yaml` file:

```yaml
name: YourName
tts_voice: onyx  # or echo, fable, nova, shimmer, alloy
tts_speed: 1.0  # Optional: 0.25 to 4.0 (slower for dignified, faster for manic)
tts_style: "Speak warmly and conversationally"  # Optional: tone/style instruction
wake_word_model: hey_yourname.onnx

system_prompt: |
  You are YourName, a character description...
  Keep responses conversational and concise.

filler_phrases:
  - "Your filler phrase 1..."
  - "Your filler phrase 2..."
```

No programming required - just copy an existing personality folder and edit the YAML file!

## Architecture

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design, component descriptions, and technical specifications.

### Key Components

1. **State Machine**: Manages conversation flow (IDLE → LISTENING → PROCESSING → SPEAKING)
2. **Wake Word Detector**: Always-on personality-specific wake word detection (OpenWakeWord)
3. **Audio Input Pipeline**: Microphone capture with voice activity detection
4. **Speech-to-Text**: OpenAI Whisper transcription
5. **Conversation Engine**: GPT-4o integration with word-based streaming chunking (MIN_CHUNK_WORDS configurable)
6. **Text-to-Speech**: OpenAI TTS synthesis with personality-specific voices and styles
7. **RVC Voice Converter** (Optional): Transforms TTS output with trained voice models for unique character voices
8. **PPM Generator**: Creates precise PPM control signals (60Hz, 400µs pulses, 630-1590µs gaps)
9. **Device Output Processors**: Device-specific audio processing (Teddy Ruxpin with PPM, Squawkers McCaw simple stereo)
10. **Audio Output Pipeline**: Stereo playback with parallel chunk processing for minimal latency

## Troubleshooting

### Wake Word Not Detecting

- **Issue**: Wake word not recognized
- **Solutions**:
  - Check microphone is working and selected correctly
  - Speak clearly and slightly louder
  - Ensure wake word model files exist in `models/` directory
  - See `docs/TRAIN_WAKE_WORDS.md` for training custom wake words

### Audio Device Issues

- **Issue**: No audio output or "Device not found"
- **Solutions**:
  - Run `python -m jf_sebastian.modules.audio_output` to list devices
  - Verify device indices in `.env`
  - Check Bluetooth connection to cassette adapter
  - Try `-1` for default device first

### API Errors

- **Issue**: "OpenAI API error" or rate limit
- **Solutions**:
  - Verify `OPENAI_API_KEY` is correct and has credits
  - Check internet connection
  - Wait if rate limited (free tier limits)
  - Review logs in `jf_sebastian.log`

### Teddy Not Moving

- **Issue**: Audio plays but Teddy doesn't move
- **Solutions**:
  - Verify stereo output is working (both channels)
  - Check Bluetooth adapter is properly inserted
  - Test with original cassette tape first
  - Verify PPM control signal generation (enable debug audio)
  - Check motor batteries in Teddy
  - Inspect output WAV file in Audacity: RIGHT channel should show regular 60Hz pulses

### Latency Issues

- **Issue**: Slow response times
- **Solutions**:
  - Use faster models: `TTS_MODEL=tts-1` (not `tts-1-hd`)
  - Check internet connection speed
  - Reduce `MAX_HISTORY_LENGTH` for shorter context
  - Consider local Whisper (whisper.cpp) instead of API

## Debug Mode

Enable detailed logging and audio file saving:

```bash
# In .env
DEBUG_MODE=true
SAVE_DEBUG_AUDIO=true
DEBUG_AUDIO_PATH=./debug_audio/
```

This will:
- Save input audio as `input_YYYYMMDD_HHMMSS.wav`
- Save stereo output as `output_YYYYMMDD_HHMMSS.wav`
- Enable verbose logging to console and `jf_sebastian.log`

Inspect stereo output in Audacity:
1. Open output WAV file
2. Split stereo to mono tracks
3. LEFT = voice audio
4. RIGHT = PPM control signal (should show regular 60Hz negative pulses with varying gap widths)

## Development

### Project Structure

```
jf-sebastian/
├── jf_sebastian/            # Main application package
│   ├── __init__.py
│   ├── main.py              # Main application
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Configuration management
│   ├── devices/             # Modular output device architecture
│   │   ├── __init__.py
│   │   ├── base.py          # OutputDevice abstract class
│   │   ├── factory.py       # Device registry and factory
│   │   ├── teddy_ruxpin.py  # Teddy Ruxpin device (with PPM)
│   │   ├── squawkers_mccaw.py  # Squawkers McCaw device (simple stereo)
│   │   └── shared/          # Shared utilities for all devices
│   │       ├── __init__.py
│   │       ├── audio_processor.py     # MP3→PCM conversion
│   │       └── sentiment_analyzer.py  # Sentiment analysis
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── state_machine.py           # State management
│   │   ├── wake_word.py               # Wake word detection
│   │   ├── audio_input.py             # Microphone + VAD
│   │   ├── speech_to_text.py          # Whisper API
│   │   ├── conversation.py            # GPT-4o integration
│   │   ├── text_to_speech.py          # TTS API
│   │   ├── filler_phrases.py          # Filler phrase manager
│   │   ├── ppm_generator.py           # PPM signal generation (60Hz)
│   │   ├── animatronic_control.py     # Legacy (deprecated)
│   │   └── audio_output.py            # Stereo playback
│   └── utils/
│       └── audio_device_utils.py
├── personalities/           # Device-agnostic personality system
│   ├── __init__.py
│   ├── README.md            # Personality creation guide
│   ├── base.py              # Personality loader (reads YAML)
│   ├── johnny/              # Johnny personality (drop-in folder)
│   │   ├── personality.yaml # Personality definition
│   │   ├── hey_johnny.onnx  # Wake word model
│   │   └── filler_audio/    # Device-specific filler audio
│   │       ├── teddy_ruxpin/
│   │       │   ├── filler_01.wav
│   │       │   ├── filler_02.wav
│   │       │   └── ...
│   │       └── squawkers_mccaw/
│   │           ├── filler_01.wav
│   │           ├── filler_02.wav
│   │           └── ...
│   ├── mr_lincoln/          # Mr. Lincoln personality (drop-in folder)
│   │   ├── personality.yaml
│   │   ├── hey_mr_lincoln.onnx
│   │   └── filler_audio/    # Device-specific filler audio
│   └── leopold/             # Leopold personality (drop-in folder)
│       ├── personality.yaml
│       ├── hey_leopold.onnx
│       └── filler_audio/    # Device-specific filler audio
├── tests/                   # Unit tests
│   ├── personalities/
│   ├── modules/
│   └── config/
├── scripts/
│   ├── generate_fillers.py  # Generate personality filler audio
│   └── test_microphone.py   # Microphone testing utility
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CREATING_PERSONALITIES.md
│   ├── QUICKSTART.md
│   └── TRAIN_WAKE_WORDS.md
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

### Running Tests

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests
pytest tests/
```

### Adding Features

The modular architecture makes it easy to extend:

- **New personalities**: See [docs/CREATING_PERSONALITIES.md](docs/CREATING_PERSONALITIES.md) for a complete guide
- **Custom wake words**: Train using OpenWakeWord (see [docs/TRAIN_WAKE_WORDS.md](docs/TRAIN_WAKE_WORDS.md))
- **Different filler phrases**: Edit your personality's `filler_phrases` in the YAML file
- **Improved lip sync**: Adjust syllable detection in `ppm_generator.py`
- **Alternative PPM timing**: Modify timing parameters in `PPMGenerator.__init__()`

## Performance Metrics

Target latencies (typical):
- Wake word detection: <500ms
- Filler phrase playback: Immediate (0.5-second natural pause + 8-15 second filler)
- Speech transcription: 1-2 seconds (during filler)
- GPT-4o-mini response: 1-2 seconds (during filler)
- TTS synthesis: 1-2 seconds (during filler)
- **Total response time**: Feels nearly instant due to fillers, actual processing 4-6 seconds

## Cost Estimates

OpenAI API usage (approximate):
- Whisper: $0.006 per minute of audio
- GPT-4o-mini: $0.001-0.005 per conversation turn (much cheaper than GPT-4o)
- TTS: $0.015 per 1000 characters

Typical conversation (10 exchanges): ~$0.20-0.40

## About the Name

This project is named after J.F. Sebastian, the genetic designer from Blade Runner (1982) who creates synthetic companions in his lonely apartment. Like Sebastian, this project is about bringing personality and life to inanimate friends.

*"I think, Sebastian, therefore I am."* — Pris

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Teddy Ruxpin is a trademark of Wicked Cool Toys. This project is not affiliated with or endorsed by Wicked Cool Toys.

## Credits

- Named after J.F. Sebastian from Blade Runner (1982)
- Built with Python, OpenAI APIs, and OpenWakeWord
- Inspired by the classic 1985 Teddy Ruxpin animatronic
- Uses VADER sentiment analysis, syllable-based lip sync, and WebRTC VAD
- PPM format based on analysis of Svengali and original Teddy Ruxpin tapes

## Contributing

Contributions welcome! Areas for improvement:
- Additional personalities (scientists, artists, historians, etc.)
- New output device types (Cricket, Grubby, other animatronics)
- Local wake word detection (OpenWakeWord)
- Local Whisper (whisper.cpp)
- Phoneme-based lip sync (more precise than syllables)
- Web interface for monitoring conversations
- Real-time PPM waveform visualization
- Multi-language support

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review logs in `jf_sebastian.log`
3. Enable debug mode for detailed diagnostics
4. Open an issue on GitHub

---

*"It's not an easy thing to meet your maker."* — Roy Batty

**Make friends. Make them talk.** 🤖✨
