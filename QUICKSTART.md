# Quick Start Guide

Get Teddy Ruxpin talking in 5 minutes!

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

Edit `.env` and add your keys:

```bash
# Get from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-key-here

# Get from https://console.picovoice.ai/
PICOVOICE_ACCESS_KEY=your-key-here
```

## 3. Configure Audio Devices

From the device list shown during setup, update `.env`:

```bash
INPUT_DEVICE_INDEX=0   # Your microphone
OUTPUT_DEVICE_INDEX=2  # Your Bluetooth cassette adapter
```

## 4. Run the Application

```bash
./run.sh
```

## 5. Talk to Teddy

1. Say: **"Hey, Teddy"**
2. Speak your message
3. Wait for Teddy to respond
4. Continue the conversation!

## Troubleshooting

### Wake word not working?
- Try saying "computer" instead (built-in wake word)
- Speak clearly and slightly louder
- Check microphone permissions

### No audio output?
- Verify Bluetooth connection
- Try `OUTPUT_DEVICE_INDEX=-1` for default device
- Run `python -m teddy_ruxpin.modules.audio_output` to re-list devices

### API errors?
- Check internet connection
- Verify API keys are correct
- Ensure OpenAI account has credits

## Next Steps

- Read [README.md](README.md) for full documentation
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- Enable debug mode to troubleshoot: `DEBUG_MODE=true` in `.env`
- Customize Teddy's personality in `teddy_ruxpin/config/settings.py`

---

**Have fun with Teddy!** 🧸
