# Quick Start Guide

*"I make friends. They're toys. My friends are toys. I make them."*

Get your animatronic AI companion talking in 5 minutes!

## 1. Install Dependencies

```bash
./setup.sh
```

This will:
- Create Python virtual environment
- Install all Python packages
- Install system dependencies (PortAudio, FFmpeg)
- Create configuration file
- List available audio devices

## 2. Configure API Keys

Edit `.env` and add your OpenAI API key:

```bash
# Get from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-key-here
```

## 3. Choose Your Personality

Set which personality you want to use in `.env`:

```bash
# Options: 'johnny' (tiki bartender), 'mr_lincoln' (Abraham Lincoln), 'leopold' (conspiracy theorist)
PERSONALITY=johnny
```

Each personality has:
- Unique voice and speaking style
- Custom wake word phrase
- Personality-specific filler phrases
- Tailored conversational behavior

## 4. Configure Audio Devices

From the device list shown during setup, find your device names and update `.env`:

```bash
INPUT_DEVICE_NAME=MacBook Air Microphone
OUTPUT_DEVICE_NAME=Arsvita
```

**Test Your Microphone:**

```bash
python scripts/test_microphone.py
```

## 5. Generate Filler Phrases

Filler phrases provide low-latency responses while processing:

```bash
python scripts/generate_fillers.py --personality johnny
```

This creates 8-15 second audio clips that play immediately when you speak, making conversations feel more natural and responsive.

## 6. Run the Application

```bash
./run.sh
```

You should see:
```
J.F. Sebastian - Animatronic AI Conversation System
"I make friends. They're toys. My friends are toys."
========================================
System ready! Say 'Hey, Johnny' to start talking.
Press Ctrl+C to exit.
```

## 7. Start Talking

**For Johnny (Tiki Bartender):**
1. Say: **"Hey, Johnny"**
2. Speak your message
3. Wait for Johnny to respond
4. Continue the conversation!

**For Mr. Lincoln (Abraham Lincoln):**
1. Say: **"Hey, Mr. Lincoln"**
2. Speak your message
3. Wait for Mr. Lincoln to respond
4. Continue the conversation!

**For Leopold (Conspiracy Theorist):**
1. Say: **"Hey, Leopold"**
2. Speak your message
3. Wait for Leopold to respond
4. Continue the conversation!

## Troubleshooting

### Wake word not working?
- Speak clearly and slightly louder
- Check microphone permissions in System Settings
- Try adjusting `VAD_AGGRESSIVENESS` in `.env` (0-3)
- Verify your microphone device is correctly configured

### No audio output?
- Verify Bluetooth connection (if using wireless adapter)
- Check device name in `.env`
- Try leaving `OUTPUT_DEVICE_NAME` empty to use system default device
- Run setup again to re-list devices: `./setup.sh`

### No filler phrases playing?
- Run: `python scripts/generate_fillers.py --personality johnny`
- Check that `personalities/johnny/filler_audio/` directory exists and contains .wav files
- Enable debug logging: `LOG_LEVEL=DEBUG` in `.env`

### API errors?
- Check internet connection
- Verify API key is correct
- Ensure OpenAI account has credits

### Audio device errors (OSError -9986)?
- Restart the application
- Check device name matches exactly (case-insensitive partial match works)
- Try using device index instead of name
- On macOS: Check System Settings > Privacy & Security > Microphone

## Advanced Configuration

### Adjust Response Timing
- `SILENCE_TIMEOUT`: How long to wait for speech (default: 10.0 seconds)
- `CONVERSATION_TIMEOUT`: When to clear conversation history (default: 120.0 seconds)

### Animatronic Control
- `MOUTH_SMOOTHING`: Lip sync smoothness (0.0-1.0, default: 0.7)
- `CONTROL_CARRIER_FREQ`: PPM carrier frequency (default: 60 Hz)
- `EYE_BLINK_MIN/MAX`: Eye blink interval range (default: 3.0-5.0 seconds)

### Debug Mode
Enable detailed logging and save audio files:
```bash
DEBUG_MODE=true
SAVE_DEBUG_AUDIO=true
LOG_LEVEL=DEBUG
```

Recorded audio will be saved to `./debug_audio/`

## Next Steps

- Read [README.md](../README.md) for full documentation
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- Create custom personalities (see [CREATING_PERSONALITIES.md](CREATING_PERSONALITIES.md))
- Experiment with different GPT models in `.env`

---

*"The light that burns twice as bright burns half as long, and you have burned so very, very brightly."*
