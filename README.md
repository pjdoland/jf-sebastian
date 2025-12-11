# J.F. Sebastian

> *"I make friends. They're toys. My friends are toys. I make them. It's a hobby."*
> — J.F. Sebastian, Blade Runner

An AI conversation system that brings life to vintage animatronic toys. Built for the 1985 Teddy Ruxpin, this system enables real-time voice conversations with ChatGPT, featuring a modular personality system with unique wake words, voices, and conversational styles.

Includes three distinct personalities: a tiki bartender, Abraham Lincoln (a homage to Disney's pioneering animatronics), and an eccentric conspiracy theorist. Add your own personalities using simple YAML files - no programming required!

## Features

- **Modular Personality System**: Switch between different AI personalities with unique voices and behaviors
  - **Johnny**: Tiki bartender with deep knowledge of tiki culture ("Hey, Johnny")
  - **Mr. Lincoln**: Abraham Lincoln, 16th President - homage to Disney's animatronics ("Hey, Mr. Lincoln")
  - **Leopold**: Eccentric conspiracy theorist with a wild backstory ("Hey, Leopold")
- **Wake Word Activation**: Custom wake words per personality using OpenWakeWord (free & open source)
- **Low-Latency Fillers**: Pre-generated personality-specific phrases play immediately while processing
- **Speech Recognition**: OpenAI Whisper API for accurate speech-to-text transcription
- **AI Conversation**: GPT-4o-mini powers personality-driven responses with conversation context
- **Natural Voice**: OpenAI TTS generates speech with personality-specific voices
- **Animatronic Control**: Generates PPM control signals for mouth (syllable-based lip sync) and eyes (sentiment-based)
- **Stereo Output**: LEFT channel = voice audio, RIGHT channel = PPM motor control signals (60Hz, 16.6ms frames)

## System Requirements

### Software
- Python 3.10 or higher
- macOS (currently configured for Mac audio devices)
- Internet connection for OpenAI APIs

### Hardware
- **1985 Teddy Ruxpin doll** (cassette-based model)
- **Bluetooth cassette adapter** (recommended: [Arsvita Car Audio Bluetooth Wireless Cassette Receiver](https://www.amazon.com/dp/B085C7GTBD))
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

### 1. Clone the Repository

```bash
git clone https://github.com/pjdoland/jf-sebastian.git
cd jf-sebastian
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Download OpenWakeWord Preprocessing Models

OpenWakeWord requires preprocessing models that must be downloaded separately:

```bash
python3 -c "from openwakeword import utils; utils.download_models(['alexa'])"
```

This downloads the required `melspectrogram.onnx` and `embedding_model.onnx` files to the openwakeword package directory.

### 5. Install System Dependencies

For audio processing, you may need additional system libraries:

```bash
# macOS
brew install portaudio ffmpeg

# The application uses:
# - PortAudio (for PyAudio)
# - FFmpeg (for MP3 to PCM conversion)
```

### 6. Configuration

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```bash
# Personality Selection
PERSONALITY=johnny  # Options: 'johnny' or 'rich'

# Required API Keys
OPENAI_API_KEY=sk-your-openai-api-key

# Audio device names (see "Finding Audio Devices" below)
INPUT_DEVICE_NAME=MacBook Air Microphone
OUTPUT_DEVICE_NAME=Arsvita
```

### 7. Get API Keys

#### OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Add to `.env` as `OPENAI_API_KEY`

#### Wake Word Models (OpenWakeWord)

No API key required! OpenWakeWord is completely free and open source.

Each personality includes its own wake word model file:
- Johnny: `personalities/johnny/hey_johnny.onnx`
- Mr. Lincoln: `personalities/mr_lincoln/hey_mr_lincoln.onnx`
- Leopold: `personalities/leopold/hey_leopold.onnx`

To create a custom wake word for a new personality:
1. Follow the guide in `docs/TRAIN_WAKE_WORDS.md`
2. Train a model for your desired wake phrase
3. Place the `.onnx` model file in your personality's directory

### 8. Finding Audio Devices

Run the audio output utility to list all devices:

```bash
python -m teddy_ruxpin.modules.audio_output
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
- **Character**: Laid-back bartender with deep tiki culture knowledge
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

### Switching Personalities

Edit `.env` to change personalities:

```bash
# Switch to Johnny
PERSONALITY=johnny

# Switch to Mr. Lincoln
PERSONALITY=mr_lincoln

# Switch to Leopold
PERSONALITY=leopold
```

Then restart the application. See `personalities/README.md` for detailed instructions on creating new personalities.

Personalities are simple YAML files - no coding required! Just copy an existing personality folder and modify the `personality.yaml` file.

### Generating Filler Audio

After creating a new personality or switching personalities, generate the filler audio files:

```bash
source venv/bin/activate
python scripts/generate_fillers.py
```

This creates 30 pre-recorded WAV files with PPM control tracks for instant playback.

## Usage

### Starting the Application

```bash
python -m teddy_ruxpin.main
```

You should see (example with Rich personality):
```
================================================================================
J.F. Sebastian - Animatronic AI Conversation System
"I make friends. They're toys. My friends are toys."
================================================================================
Personality: Rich
Wake word: Hey Rich
...
System ready! Say 'Hey, Rich' to start talking.
Press Ctrl+C to exit.
================================================================================
```

### Having a Conversation

1. **Wake the character**: Say the wake word ("Hey, Johnny" or "Hey, Rich")
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

| Setting | Description | Default |
|---------|-------------|---------|
| `PERSONALITY` | Active personality ('johnny' or 'rich') | johnny |
| `OPENAI_API_KEY` | OpenAI API key (required) | - |
| `INPUT_DEVICE_NAME` | Microphone device name | - |
| `OUTPUT_DEVICE_NAME` | Speaker device name | - |
| `SAMPLE_RATE` | Audio sample rate (Hz) | 16000 |
| `VAD_AGGRESSIVENESS` | Voice activity detection (0-3) | 3 |
| `SILENCE_TIMEOUT` | Max silence before timeout (seconds) | 10.0 |
| `CONVERSATION_TIMEOUT` | Clear history after idle (seconds) | 120.0 |
| `GPT_MODEL` | OpenAI GPT model | gpt-4o-mini |
| `SENTIMENT_POSITIVE_THRESHOLD` | Eye control threshold | 0.3 |
| `SENTIMENT_NEGATIVE_THRESHOLD` | Eye control threshold | -0.3 |
| `DEBUG_MODE` | Enable debug logging | false |
| `SAVE_DEBUG_AUDIO` | Save audio files for debugging | false |

**Note**: TTS voice and system prompt are now defined per personality in `personalities/`

### Creating Custom Personalities

Creating a new personality is easy - just create a folder and a YAML file!

**📖 Full Guide:** See [docs/CREATING_PERSONALITIES.md](docs/CREATING_PERSONALITIES.md) for a comprehensive step-by-step guide.

**Quick Reference:** See `personalities/README.md` for technical details.

Each personality is defined in a simple `personality.yaml` file:

```yaml
name: YourName
tts_voice: onyx  # or echo, fable, nova, shimmer, alloy
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

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design, component descriptions, and technical specifications.

### Key Components

1. **State Machine**: Manages conversation flow (IDLE → LISTENING → PROCESSING → SPEAKING)
2. **Wake Word Detector**: Always-on "Hey, Teddy" detection
3. **Audio Input Pipeline**: Microphone capture with voice activity detection
4. **Speech-to-Text**: OpenAI Whisper transcription
5. **Conversation Engine**: GPT-4o integration with context management
6. **Text-to-Speech**: OpenAI TTS synthesis
7. **PPM Generator**: Creates precise PPM control signals (60Hz, 400µs pulses, 630-1590µs gaps)
8. **Animatronic Control Generator**: Syllable-based lip sync and sentiment-based eye control
9. **Audio Output Pipeline**: Stereo playback to Teddy (44.1kHz native for PPM precision)

## Troubleshooting

### Wake Word Not Detecting

- **Issue**: "Hey, Johnny" or "Hey, Rich" not recognized
- **Solutions**:
  - Check microphone is working and selected correctly
  - Speak clearly and slightly louder
  - Ensure wake word model files exist in `models/` directory
  - See `docs/TRAIN_WAKE_WORDS.md` for training custom wake words

### Audio Device Issues

- **Issue**: No audio output or "Device not found"
- **Solutions**:
  - Run `python -m teddy_ruxpin.modules.audio_output` to list devices
  - Verify device indices in `.env`
  - Check Bluetooth connection to cassette adapter
  - Try `-1` for default device first

### API Errors

- **Issue**: "OpenAI API error" or rate limit
- **Solutions**:
  - Verify `OPENAI_API_KEY` is correct and has credits
  - Check internet connection
  - Wait if rate limited (free tier limits)
  - Review logs in `teddy_ruxpin.log`

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
- Enable verbose logging to console and `teddy_ruxpin.log`

Inspect stereo output in Audacity:
1. Open output WAV file
2. Split stereo to mono tracks
3. LEFT = voice audio
4. RIGHT = PPM control signal (should show regular 60Hz negative pulses with varying gap widths)

## Development

### Project Structure

```
jf-sebastian/
├── teddy_ruxpin/
│   ├── __init__.py
│   ├── main.py              # Main application
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py      # Configuration management
│   ├── personalities/       # Modular personality system
│   │   ├── __init__.py
│   │   ├── README.md        # Personality creation guide
│   │   ├── base.py          # Personality loader (reads YAML)
│   │   ├── johnny/          # Johnny personality (drop-in folder)
│   │   │   ├── personality.yaml   # Personality definition
│   │   │   ├── hey_johnny.onnx    # Wake word model
│   │   │   └── filler_audio/
│   │   │       ├── filler_01.wav
│   │   │       ├── filler_02.wav
│   │   │       └── ...
│   │   ├── mr_lincoln/      # Mr. Lincoln personality (drop-in folder)
│   │   │   ├── personality.yaml   # Personality definition
│   │   │   ├── hey_mr_lincoln.onnx # Wake word model
│   │   │   └── filler_audio/
│   │   └── leopold/         # Leopold personality (drop-in folder)
│   │       ├── personality.yaml   # Personality definition
│   │       ├── hey_leopold.onnx   # Wake word model
│   │       └── filler_audio/
│   └── modules/
│       ├── __init__.py
│       ├── state_machine.py           # State management
│       ├── wake_word.py               # Wake word detection
│       ├── audio_input.py             # Microphone + VAD
│       ├── speech_to_text.py          # Whisper API
│       ├── conversation.py            # GPT-4o integration
│       ├── text_to_speech.py          # TTS API
│       ├── filler_phrases.py          # Filler phrase manager
│       ├── ppm_generator.py           # PPM signal generation (60Hz)
│       ├── animatronic_control.py     # Syllable-based lip sync + sentiment
│       └── audio_output.py            # Stereo playback
├── scripts/
│   └── generate_fillers.py  # Generate personality filler audio
├── requirements.txt
├── .env.example
├── README.md
└── ARCHITECTURE.md
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

This project is for educational and personal use. Teddy Ruxpin is a trademark of Wicked Cool Toys.

## Credits

- Named after J.F. Sebastian from Blade Runner (1982)
- Built with Python, OpenAI APIs, and OpenWakeWord
- Inspired by the classic 1985 Teddy Ruxpin animatronic
- Uses VADER sentiment analysis, syllable-based lip sync, and WebRTC VAD
- PPM format based on analysis of Svengali and original Teddy Ruxpin tapes

## Contributing

Contributions welcome! Areas for improvement:
- Additional personalities (scientists, artists, historians, etc.)
- Local wake word detection (OpenWakeWord)
- Local Whisper (whisper.cpp)
- Phoneme-based lip sync (more precise than syllables)
- Support for other animatronics (Cricket, Grubby, etc.)
- Web interface for monitoring conversations
- Real-time PPM waveform visualization
- Multi-language support

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review logs in `teddy_ruxpin.log`
3. Enable debug mode for detailed diagnostics
4. Open an issue on GitHub

---

*"It's not an easy thing to meet your maker."* — Roy Batty

**Make friends. Make them talk.** 🤖✨
