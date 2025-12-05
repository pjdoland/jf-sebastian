# Teddy Ruxpin AI Conversation System - Architecture

## System Overview

This application enables real-time voice conversations with ChatGPT through a 1985 Teddy Ruxpin animatronic using wake word activation.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Main Application                        │
│                   (State Machine Manager)                   │
└───────┬─────────────────────────────────────────────────────┘
        │
        ├─► Wake Word Detector (Porcupine/OpenWakeWord)
        │   - Always-on listening
        │   - "Hey, Teddy" detection
        │   - Triggers state transition: IDLE → LISTENING
        │
        ├─► Audio Input Pipeline
        │   - Microphone capture (PyAudio/sounddevice)
        │   - Voice Activity Detection (WebRTC VAD)
        │   - Buffer management
        │
        ├─► Speech-to-Text Module
        │   - OpenAI Whisper API
        │   - Transcription processing
        │   - Error handling
        │
        ├─► Conversation Engine
        │   - OpenAI GPT-4o API
        │   - Context management
        │   - System prompt injection
        │   - Response generation
        │
        ├─► Text-to-Speech Module
        │   - OpenAI TTS API
        │   - Voice audio generation
        │   - Audio format handling
        │
        ├─► PPM Generator
        │   - 60Hz frame rate (16.6ms periods)
        │   - 8-channel PPM encoding (400µs pulses, 630-1590µs gaps)
        │   - Syllable-based mouth value calculation
        │   - Generated at 44.1kHz for precision
        │
        ├─► Animatronic Control Generator
        │   - Mouth control (syllable-based lip sync with PPM)
        │   - Eye control (sentiment-based positioning)
        │   - Stereo channel mixing (LEFT=voice, RIGHT=PPM)
        │
        └─► Audio Output Pipeline
            - Stereo output routing at 44.1kHz
            - LEFT: Voice audio to Teddy speaker
            - RIGHT: PPM control signals to motors
            - Automatic device sample rate handling
```

## State Machine

```
┌──────┐     wake word      ┌───────────┐
│ IDLE ├──────────────────► │ LISTENING │
└──┬───┘                    └──────┬────┘
   ▲                               │
   │                               │ silence timeout (10s)
   │                               │ OR speech ended
   │                               ▼
   │                        ┌────────────┐
   │                        │ PROCESSING │
   │                        └──────┬─────┘
   │                               │
   │                               │ GPT response ready
   │                               ▼
   │       response complete  ┌──────────┐
   └──────────────────────────┤ SPEAKING │
                              └──────────┘
```

### State Descriptions

**IDLE**
- Only wake word detection active
- Minimal CPU usage
- No audio recording beyond wake word buffer
- Conversation history cleared after 2 min idle

**LISTENING**
- Microphone actively recording
- VAD monitoring for speech end
- Audio buffered for transcription
- 10-second silence timeout
- Visual: Teddy mouth open slightly (attentive)

**PROCESSING**
- Transcribing speech via Whisper
- Sending to GPT-4o
- Generating TTS audio
- Creating control signals
- Visual: Teddy eyes thinking position

**SPEAKING**
- Playing stereo audio output
- LEFT: Voice audio to speaker
- RIGHT: Control signals to motors
- Blocking until complete
- Returns to IDLE when finished

## Audio Signal Architecture

### Stereo Channel Design

```
TTS Audio (MP3) ──► [FFmpeg Decode] ──► PCM Audio @ 16kHz
                            │
                            ├──► [Resample to 44.1kHz] ──► LEFT CHANNEL (Voice)
                            │
                            ├──► [Syllable Parser] ──► [Mouth Values per Syllable]
                            │                                     │
                            └──► [Sentiment Analysis] ──► [Eye Position Values]
                                                                  │
                                    ┌─────────────────────────────┘
                                    ▼
                            [PPM Generator @ 44.1kHz]
                            - Ch1: Eyes (sentiment)
                            - Ch2: Upper jaw (70% of Ch3)
                            - Ch3: Lower jaw (syllable-based)
                                    │
                                    ▼
                           RIGHT CHANNEL (PPM Control @ 60Hz)
```

### Control Signal Generation - PPM Format

**PPM (Pulse Position Modulation) Format**
- Frame rate: 60Hz (16.6ms frame period)
- 8 channels per frame
- Channel 1: Eyes
- Channel 2: Upper jaw
- Channel 3: Lower jaw (primary mouth control)
- Channels 4-8: Reserved/unused

**PPM Timing (per channel)**
- Pulse: 400µs at -30% amplitude (negative-going)
- Gap: 630µs to 1590µs (DC center, 0.0)
- Gap duration encodes motor position (0-255 maps to min-max gap)
- Generated at 44.1kHz for precise pulse timing
- Low-pass filtered at 5kHz (2nd order Butterworth) for smooth edges

**Mouth Control (Syllable-Based)**
- Parse response text into syllables using `syllables` library
- Divide audio waveform into syllable segments
- Calculate one mouth opening value per syllable:
  - Peak amplitude: `max(abs(syllable_audio))`
  - RMS amplitude: `sqrt(mean(syllable_audio²))`
  - Blended: `0.7 * peak + 0.3 * rms`
  - Scaled and clipped: `clip(amplitude * 5.0, 0, 1) ** 0.75`
- Apply smooth transitions between syllables:
  - Fast attack (0.15): Syllable onset
  - Slower release (0.35): Between syllables
- Encode to PPM: Ch3 (lower jaw) = mouth_value * 255, Ch2 (upper jaw) = 70% of Ch3

**Eye Control (Sentiment-Based)**
- Analyze GPT response sentiment using VADER
- Map sentiment (-1 to 1) to eye position (0 to 1):
  - Base position: 0.5 (center)
  - Sentiment modulation: ±30% (0.5 + sentiment * 0.3)
  - Clipped to valid range [0, 1]
- Add occasional blinks: 0.5% chance per frame (~once per 10 seconds)
- Encode to PPM: Ch1 = eye_position * 255

### 1985 Teddy Ruxpin Technical Specs

The original mechanism uses:
- Cassette tape stereo channels
- LEFT: Audio playback
- RIGHT: PPM control track with pulse-position-encoded servo positions
- Sampling rate: 44.1kHz for modern digital playback (preserves PPM timing)
- Motor response time: ~50-100ms (one PPM frame = 16.6ms)
- Mouth: Controlled by Ch2 (upper jaw) and Ch3 (lower jaw) PPM values
- Eyes: Controlled by Ch1 PPM value

### Sample Rate Architecture

- **Processing**: 16kHz (WebRTC VAD compatibility, efficient Whisper input)
- **PPM Generation**: 44.1kHz (precise pulse timing, no resampling artifacts)
- **Voice Resampling**: Voice audio resampled from 16kHz to 44.1kHz to match PPM
- **Output**: 44.1kHz stereo (native device rate, no additional resampling)

**Why resample voice and not PPM?**
- PPM pulses are 400µs (17.6 samples at 44.1kHz)
- FFT resampling introduces ringing around sharp edges
- Resampling voice audio preserves PPM signal integrity

## Latency Targets

- Wake word → Acknowledgment: <500ms
- Speech end → GPT request: <200ms
- GPT → TTS → Playback start: <2 seconds
- Total: User stops speaking → Teddy starts: <2.5 seconds

## Error Handling Strategy

1. **API Failures**
   - Retry logic with exponential backoff
   - Fallback responses ("I'm having trouble thinking right now")
   - Log errors for debugging

2. **Audio Device Issues**
   - Graceful device enumeration
   - Clear error messages for device selection
   - Fallback to default device

3. **Wake Word False Positives**
   - Require minimum audio energy threshold
   - Confirmation beep so user knows detection occurred

4. **Network Issues**
   - Queue requests during outages
   - Timeout handling
   - User notification via audio cue

## Configuration Management

Using `.env` file for:
- OpenAI API key
- Picovoice/OpenWakeWord credentials
- Audio device indices
- Timing thresholds
- Model selections
- Debug flags

## Dependencies

Core libraries:
- `pvporcupine` or `openwakeword` - Wake word detection
- `pyaudio` or `sounddevice` - Audio I/O
- `webrtcvad` - Voice activity detection
- `openai` - Whisper, GPT-4o, TTS APIs
- `numpy` - Audio signal processing
- `scipy` - Signal filtering, resampling, and PPM waveform generation
- `syllables` - Syllable detection for lip sync timing
- `pyphen` - Syllable parsing support
- `vaderSentiment` - Sentiment analysis for eye control
- `python-dotenv` - Configuration management
- `threading` / `queue` - Concurrent processing

## Threading Model

```
Main Thread
├─► Wake Word Thread (continuous listening)
├─► Audio Input Thread (recording during LISTENING)
└─► Audio Output Thread (playback during SPEAKING)

Async/Queue Communication:
- Wake word event → State machine
- Audio chunks → Processing pipeline
- TTS output → Playback queue
```

## Testing Strategy

Phase 1: Individual modules
- Wake word detection accuracy
- Speech-to-text quality
- GPT response appropriateness
- TTS audio quality

Phase 2: Control signal generation
- PPM signal format validation (60Hz frame rate, correct pulse/gap timing)
- Syllable-based mouth sync accuracy
- Eye sentiment mapping
- Signal integrity (no resampling artifacts)

Phase 3: Integration testing
- End-to-end conversation flow
- Latency measurements
- Error recovery
- Sustained operation

Phase 4: Hardware validation
- Teddy Ruxpin physical response
- Audio quality through cassette adapter
- Motor synchronization
- Real-world conversation testing
