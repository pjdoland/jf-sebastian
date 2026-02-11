# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

J.F. Sebastian is an AI-powered animatronic conversation system that brings vintage animatronic toys to life through real-time voice interactions. The system enables personality-driven conversations with ChatGPT through devices like the 1985 Teddy Ruxpin doll, featuring speech recognition, text-to-speech synthesis, and optional voice conversion.

**Critical Requirements:**
- Python 3.10.x specifically (RVC dependencies incompatible with 3.11+)
- macOS environment (currently configured for Mac audio devices)
- OpenAI API key required for Whisper, GPT-4o-mini, and TTS

## Essential Commands

### Setup and Installation
```bash
# Automated setup (recommended)
./setup.sh

# Manual virtual environment setup
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install RVC (optional, requires Python 3.10)
./scripts/install_rvc.sh
# OR manually:
pip install pip==24.0
pip install -r requirements-rvc.txt
pip install --upgrade pip

# Download OpenWakeWord preprocessing models
python3 -c "from openwakeword import utils; utils.download_models(['alexa'])"

# List available audio devices
python -m jf_sebastian.modules.audio_output
```

### Running the Application
```bash
# Using convenience script
./run.sh

# Direct execution
python -m jf_sebastian.main
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test markers
pytest -m unit        # Unit tests only
pytest -m integration # Integration tests
pytest -m audio       # Audio-related tests
pytest -m slow        # Long-running tests

# Run tests with verbose output
pytest -v tests/

# Test specific component
pytest tests/modules/test_state_machine.py
pytest tests/personalities/test_base.py
```

### Personality Management
```bash
# Generate filler audio for all personalities
python scripts/generate_fillers.py

# Generate for specific personality
python scripts/generate_fillers.py --personality johnny

# Test microphone
python scripts/test_microphone.py

# Benchmark RVC performance
python scripts/benchmark_rvc.py
```

## Architecture Overview

### Core State Machine
The system operates through a 4-state finite state machine:
```
IDLE ──wake word──> LISTENING ──speech end──> PROCESSING ──response ready──> SPEAKING
 ▲                      │                             │                          │
 └──timeout/silence────┘─────────────────────────────┴──────────────────────────┘
```

State transitions managed in `jf_sebastian/modules/state_machine.py` (StateMachine class).

### Main Application Flow (TeddyRuxpinApp in main.py)
1. Initialize all modules (wake word detector, audio I/O, STT, LLM, TTS, device output)
2. Start in IDLE state with background wake word detection
3. On wake word: IDLE → LISTENING
4. On speech end (VAD detection): LISTENING → PROCESSING
5. Multi-stage audio validation (filters silence/noise before Whisper):
   - Length check → RMS amplitude check → VAD speech content analysis
   - Only if all checks pass: Select filler phrase → Call Whisper API
   - Transcript validation (hallucination detection as backup)
6. Parallel processing pipeline:
   - Whisper API transcribes speech (only if validation passed)
   - ConversationEngine streams GPT response with word-based chunking (MIN_CHUNK_WORDS=15)
   - TextToSpeech synthesizes each chunk (optionally through RVC)
   - Output device creates stereo audio (LEFT=voice, RIGHT=PPM control for Teddy Ruxpin)
7. AudioPlayer plays chunks: PROCESSING → SPEAKING
8. On completion: SPEAKING → LISTENING or IDLE

### Key Module Responsibilities

**jf_sebastian/modules/**
- `state_machine.py`: StateMachine class managing conversation states
- `wake_word.py`: WakeWordDetector using OpenWakeWord with debouncing (2s minimum)
- `audio_input.py`: AudioRecorder with PyAudio/sounddevice and WebRTC VAD
- `speech_to_text.py`: SpeechToText wrapping OpenAI Whisper API
- `conversation.py`: ConversationEngine managing GPT-4o-mini with streaming and word-chunked responses
- `text_to_speech.py`: TextToSpeech wrapping OpenAI TTS with per-personality voice/speed/style
- `filler_phrases.py`: FillerPhraseManager for low-latency response playback
- `ppm_generator.py`: PPMGenerator for 60Hz PPM control signals (630-1590µs pulse widths)
- `rvc_processor.py`: RVCProcessor for optional voice conversion
- `audio_output.py`: AudioPlayer for stereo playback with device enumeration

**jf_sebastian/devices/** (Modular Output Device Architecture)
- `base.py`: OutputDevice abstract base class defining the interface
- `factory.py`: DeviceRegistry providing plugin-style registration/creation
- `teddy_ruxpin.py`: TeddyRuxpinDevice generating stereo (LEFT=voice, RIGHT=PPM)
- `squawkers_mccaw.py`: SquawkersMcCawDevice for simple stereo output
- `shared/audio_processor.py`: MP3→PCM conversion via FFmpeg
- `shared/sentiment_analyzer.py`: VADER sentiment analysis for eye control

**jf_sebastian/config/**
- `settings.py`: Central Settings class loading from `.env` with validation

**jf_sebastian/utils/**
- `audio_utils.py`: Audio utility functions including `calculate_rms()` for amplitude analysis and `contains_speech()` for VAD-based speech detection

### Device Architecture Pattern
The system uses a **plugin-style device registry** allowing easy addition of new output devices:
- Inherit from `OutputDevice` abstract base class
- Implement `process_audio()` method
- Register with `@register_device('device_name')` decorator
- Device-specific processing automatically applied (PPM generation for Teddy, simple stereo for others)

### Personality System
Zero-code personality definition via YAML files in `personalities/` directory:
- Each personality is a folder with `personality.yaml`
- No Python code changes needed to add new characters
- Per-personality configuration:
  - Wake word models (ONNX files)
  - TTS voice, speed, style instructions
  - System prompt for LLM personality
  - Filler phrases for low-latency feel
  - Optional RVC voice conversion models (`*.pth`, `*.index`)
- Filler audio stored in device-specific subdirectories: `filler_audio/teddy_ruxpin/`, `filler_audio/squawkers_mccaw/`

**Available personalities:** johnny, mr_lincoln, leopold, fred, kitt, teddy_ruxpin, all_might, computer, el_rey, hal_9000, jose, rich

### Streaming Response Pipeline
Advanced **word-based sentence chunking** for parallel processing:
1. LLM streams response as tokens
2. Chunks accumulate to MIN_CHUNK_WORDS (default: 15)
3. Each complete sentence chunk triggers TTS immediately
4. TTS output optionally passes through RVC
5. PPM control signals generated in parallel
6. Chunks queued for playback while LLM continues generating
7. Results in nearly-instant perceived response despite backend processing

### PPM Control Signal Generation
Precise 60Hz PPM (Pulse Position Modulation) for animatronic motor control:
- Sample rate: 44.1kHz for precise timing
- Frame rate: 60Hz (16.67ms per frame)
- 8 channels encoded in pulse widths
- Channel 1: Mouth position (syllable-based lip sync)
- Channel 2: Eye position (sentiment-based expressions)
- Output: RIGHT channel contains PPM pulses, LEFT channel contains voice

## Critical Implementation Details

### Audio Processing
- All audio operations use 16kHz sample rate by default (configurable: 16000, 22050, 44100, 48000)
- Stereo WAV format for all output
- LEFT channel: Voice audio
- RIGHT channel: PPM control signals (Teddy Ruxpin only)
- FFmpeg required for MP3→PCM conversion

### Multi-Stage Silence Detection
The system uses a **defense-in-depth approach** to filter out silence and background noise before processing, preventing unnecessary Whisper API calls and avoiding hallucinations (false transcriptions like "Thank you", "Goodbye", etc.):

**Stage 1: Audio Length Check** (`main.py:_on_speech_end`)
- Validates minimum audio duration (MIN_LISTEN_SECONDS * sample_rate * 2 bytes)
- Filters recordings that ended too quickly (likely timeouts)
- Returns to IDLE if audio too short

**Stage 2: RMS Amplitude Check** (`main.py:_on_speech_end` → `utils/audio_utils.py:calculate_rms`)
- Analyzes peak RMS (Root Mean Square) amplitude using 100ms sliding windows
- Detects if ANY portion of the audio has sufficient volume
- Configurable threshold: `MIN_AUDIO_RMS` (default: 60, typical speech: 1500-5000)
- Filters: Pure silence, very quiet audio
- Returns to IDLE if RMS below threshold

**Stage 3: VAD Speech Content Analysis** (`main.py:_on_speech_end` → `utils/audio_utils.py:contains_speech`)
- Analyzes entire audio buffer frame-by-frame using WebRTC VAD
- Calculates percentage of frames containing actual speech vs. noise
- Configurable threshold: `MIN_SPEECH_RATIO` (default: 0.3 = 30% of frames must be speech)
- Filters: Background noise, music, rustling, humming - anything with volume but no speech
- Returns to IDLE if speech ratio below threshold
- This is the **primary defense** against Whisper hallucinations

**Stage 4: Whisper Hallucination Detection** (`main.py:_process_and_speak`)
- After transcription, checks transcript against known Whisper hallucination phrases
- Common hallucinations: "Thank you", "Goodbye", "Bye", "Thanks for watching", etc.
- Also validates transcript isn't too short or just punctuation
- Returns to IDLE if hallucination detected
- This is a **backup safety net** for edge cases that slip through VAD

**Execution Order:**
1. Stages 1-3 run **before** selecting filler phrase
2. Stages 1-3 run **before** calling Whisper API (saves API quota)
3. Only if all stages pass: Filler phrase selected → Whisper called → Stage 4 validation

**Benefits:**
- Eliminates 95%+ of false Whisper API calls
- Prevents filler phrases from playing on silence/noise
- Saves API costs by filtering before transcription
- Multi-layered validation ensures robustness

**Tuning Guide:**
- Increase `MIN_AUDIO_RMS` if transcribing too much quiet noise (typical speech: 1500-5000)
- Increase `MIN_SPEECH_RATIO` (0.4-0.5) if still getting hallucinations
- Decrease `MIN_SPEECH_RATIO` (0.2-0.25) if valid speech being rejected
- Use `VAD_AGGRESSIVENESS` (0-3) to control sensitivity (3 = most strict)

### RVC Voice Conversion
- Optional feature requiring Python 3.10.x specifically
- Warmup performed on startup to eliminate first-use delay
- Lazy import of openwakeword (heavy ML library)
- Per-personality enable/disable in `personality.yaml`
- RVC settings: `rvc_enabled`, `rvc_model_path`, `rvc_index_path`, `rvc_pitch_shift`

### Low-Latency Filler System
Pre-generated personality-specific audio fills response gap:
1. User speaks, VAD detects speech end
2. Filler phrase plays immediately (0.5s pause + 8-15s filler)
3. During filler: Whisper transcribes, GPT processes, TTS generates
4. Real response seamlessly transitions from filler
5. Creates perceived instant response despite 4-6s actual processing

### Configuration Management
- Environment-based configuration via `.env` file
- Settings class in `jf_sebastian/config/settings.py` loads with validation
- No hardcoded values - all configurable
- Per-personality settings in `personalities/{name}/personality.yaml`

## File Locations and Conventions

### Important Paths
- Main entry: `jf_sebastian/main.py`
- Configuration: `.env` (created from `.env.example`)
- Personalities: `personalities/{name}/personality.yaml`
- Wake word models: `personalities/{name}/*.onnx`
- Filler audio: `personalities/{name}/filler_audio/{device_type}/filler_*.wav`
- RVC models: `personalities/{name}/*.pth` and `*.index`
- Tests: `tests/` (mirrors `jf_sebastian/` structure)
- Debug audio: `debug_audio/` (when SAVE_DEBUG_AUDIO=true)

### Testing Structure
- `tests/conftest.py`: Test fixtures and configuration
- `tests/config/`: Settings and configuration tests
- `tests/modules/`: Core module tests (state machine, PPM, sentiment, etc.)
- `tests/devices/`: Device factory and implementation tests
- `tests/personalities/`: Personality loading and validation tests
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`, `@pytest.mark.audio`, `@pytest.mark.hardware`

## Development Guidelines

### Adding New Personalities
1. Create folder in `personalities/{name}/`
2. Create `personality.yaml` with required fields (see docs/CREATING_PERSONALITIES.md)
3. Train wake word model using OpenWakeWord (see docs/TRAIN_WAKE_WORDS.md)
4. Place `hey_{name}.onnx` in personality folder
5. Optional: Add RVC models (`{name}.pth`, `{name}.index`)
6. Generate filler audio: `python scripts/generate_fillers.py --personality {name}`
7. Set in `.env`: `PERSONALITY={name}`

### Adding New Output Devices
1. Create new file in `jf_sebastian/devices/{device_name}.py`
2. Inherit from `OutputDevice` base class
3. Implement `process_audio(audio_data: bytes, text: str) -> bytes` method
4. Register with `@register_device('device_name')` decorator
5. Device automatically available in `OUTPUT_DEVICE_TYPE` setting

### Modifying Audio Pipeline
- Audio input: Modify `jf_sebastian/modules/audio_input.py` (AudioRecorder class)
- VAD settings: Adjust in `.env` (VAD_AGGRESSIVENESS, SPEECH_END_SILENCE_SECONDS)
- PPM generation: Modify `jf_sebastian/modules/ppm_generator.py` (PPMGenerator class)
- Lip sync: Adjust syllable detection in PPMGenerator
- Eye control: Modify sentiment thresholds in `.env` or `sentiment_analyzer.py`

### Common Gotchas
- Python 3.10.x specifically required for RVC (not 3.11+)
- OpenWakeWord preprocessing models must be downloaded separately
- PortAudio and FFmpeg system dependencies required
- RVC installation requires pip downgrade to 24.0, then upgrade back
- Filler audio must be regenerated when personality settings change
- Wake word debouncing is 2 seconds minimum (hardcoded in wake_word.py)
- Sample rate must be 16000, 22050, 44100, or 48000 (WebRTC VAD constraint)

### Performance Optimization
- RVC warmup on startup eliminates first-use delay
- Lazy import of openwakeword (heavy ML library)
- Streaming response chunking enables parallel processing
- Async file I/O for audio saves
- Word-based sentence chunking (MIN_CHUNK_WORDS) balances latency vs. naturalness

## Debugging

### Enable Debug Mode
Set in `.env`:
```bash
DEBUG_MODE=true
SAVE_DEBUG_AUDIO=true
DEBUG_AUDIO_PATH=./debug_audio/
LOG_LEVEL=DEBUG
```

### Debug Audio Analysis
1. Saved files: `debug_audio/input_YYYYMMDD_HHMMSS.wav` and `output_YYYYMMDD_HHMMSS.wav`
2. Open in Audacity and split stereo to mono
3. LEFT channel: Voice audio
4. RIGHT channel: PPM control signal (should show regular 60Hz negative pulses)

### Common Issues
- **Wake word not detecting**: Check microphone selection, speak louder/clearer, verify wake word model exists
- **No audio output**: Run device enumeration, verify Bluetooth connection, check device name in `.env`
- **Teddy not moving**: Verify stereo output, check PPM signals in debug audio, test motor batteries
- **API errors**: Verify OpenAI API key, check credits, review `jf_sebastian.log`
- **Latency**: Use faster models (tts-1 not tts-1-hd), reduce MAX_HISTORY_LENGTH, check internet speed

## Reference Documentation

- `docs/ARCHITECTURE.md`: Detailed system design and component specifications
- `docs/CREATING_PERSONALITIES.md`: Step-by-step guide for adding personalities
- `docs/QUICKSTART.md`: 5-minute getting started guide
- `docs/TRAIN_WAKE_WORDS.md`: Custom wake word training instructions
- `personalities/README.md`: Technical personality system reference
