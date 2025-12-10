# Animatronic Personalities

This directory contains drop-in personality folders for the animatronic system. Each personality is completely self-contained - just add or remove folders to manage personalities!

Personalities are defined using simple YAML files - **no programming required**.

## Available Personalities

### Johnny (Tiki Bartender)
- **Wake word**: "Hey, Johnny"
- **Voice**: Onyx (male, casual)
- **Character**: Laid-back tiki bartender with deep knowledge of tiki culture, surf music, and tropical drinks
- **Filler phrases**: Bar activities like making orgeat, grabbing mint, checking rum barrels, etc.

### Mr. Lincoln (Abraham Lincoln)
- **Wake word**: "Hey, Mr. Lincoln"
- **Voice**: Echo (male, dignified)
- **Character**: 16th President of the United States - a homage to Disney's Great Moments with Mr. Lincoln
- **Filler phrases**: Consulting documents, reviewing correspondence, reflecting on the Constitution, etc.

### Leopold (Conspiracy Theorist)
- **Wake word**: "Hey, Leopold"
- **Voice**: Onyx (male, conspiratorial)
- **Character**: Eccentric truth-seeker with an insane backstory (Turkish prison, UFO abductions, intelligence contractor)
- **Filler phrases**: Checking bug detectors, scanning perimeter, reviewing surveillance footage, etc.

## Switching Personalities

To switch personalities, update the `PERSONALITY` setting in your `.env` file:

```bash
# Use Johnny the Tiki Bartender
PERSONALITY=johnny

# Use Mr. Lincoln
PERSONALITY=mr_lincoln

# Use Leopold the Conspiracy Theorist
PERSONALITY=leopold
```

## Creating a New Personality

**📖 Full Guide:** For a comprehensive step-by-step tutorial, see [docs/CREATING_PERSONALITIES.md](../../docs/CREATING_PERSONALITIES.md)

**Quick Start:** Creating a personality is simple - just create a folder and a YAML file!

### Step 1: Copy an Existing Personality

```bash
# Copy an existing personality as a template
cp -r teddy_ruxpin/personalities/johnny teddy_ruxpin/personalities/yourname
```

### Step 2: Edit personality.yaml

Open `teddy_ruxpin/personalities/yourname/personality.yaml` and customize:

```yaml
# Your personality name
name: YourName

# OpenAI TTS voice (onyx, echo, fable, nova, shimmer, or alloy)
tts_voice: onyx

# Wake word model filename (in this same directory)
wake_word_model: hey_yourname.onnx

# System prompt defining the character
system_prompt: |
  You are YourName, describe the character here...

  Keep responses conversational and concise (2-3 sentences).

  Remember: you're a physical animatronic having a real conversation.

# Filler phrases (8-10 seconds each, 30 recommended)
filler_phrases:
  - "Your first filler phrase ending with a transition word... Now..."
  - "Your second filler phrase... So..."
  - "Your third filler phrase... Alright..."
  # Add 27 more for variety!
```

### Step 3: Train Custom Wake Word
- Follow the guide in `docs/TRAIN_WAKE_WORDS.md`
- Train an OpenWakeWord model for your wake phrase (e.g., "Hey YourName")
- Save the `.onnx` model file as `hey_yourname.onnx`
- Place it in your personality's directory: `teddy_ruxpin/personalities/yourname/hey_yourname.onnx`

### Step 4: Generate Filler Audio

```bash
python scripts/generate_fillers.py --personality yourname
```

### Step 5: Activate Your Personality

Edit `.env`:
```bash
PERSONALITY=yourname
```

**That's it!** Your personality is automatically discovered and ready to use. No registration or code changes needed!

## Personality Directory Structure

Each personality is fully self-contained in its own directory:
```
yourname/
├── personality.yaml               # Personality definition (YAML - easy to edit!)
├── hey_yourname.onnx              # Wake word model
└── filler_audio/                  # Pre-generated filler audio
    ├── filler_01.wav
    ├── filler_02.wav
    └── ...
```

**Everything for a personality stays in its folder:**
- ✅ **Add a personality**: Just drop in a new folder
- ✅ **Remove a personality**: Just delete the folder
- ✅ **Share a personality**: Zip the folder and send it
- ✅ **No code changes**: Personalities are auto-discovered

The only external configuration needed is setting `PERSONALITY=yourname` in `.env`.

## Available TTS Voices

OpenAI provides these voices:
- **onyx**: Male, casual (used by Johnny)
- **echo**: Male, professional (used by Rich)
- **fable**: Male, expressive
- **nova**: Female, friendly
- **shimmer**: Female, warm
- **alloy**: Neutral

## Filler Phrases

Filler phrases play immediately after speech detection while the real response is being generated. They should:
- Be 8-10 seconds long
- End with a transition like "Now...", "So...", "Alright..."
- Reflect the character's activities and personality
- Give enough time for API processing (Whisper + GPT + TTS)

## Technical Details

### YAML Format

Personalities are defined in `personality.yaml` files with these fields:

- **`name`** (required): Character name shown to users
- **`tts_voice`** (required): OpenAI TTS voice ID
- **`wake_word_model`** (required): Filename of the .onnx wake word model
- **`system_prompt`** (required): Multi-line text defining the character's personality
- **`filler_phrases`** (required): List of 8-10 second phrases for low-latency response

### Auto-Discovery

The system automatically scans `teddy_ruxpin/personalities/` for subdirectories containing `personality.yaml` files. No manual registration needed!

### Validation

When a personality loads, the system validates:
- All required fields are present
- `filler_phrases` is a list
- Wake word model file exists
- YAML syntax is correct
