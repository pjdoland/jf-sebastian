# Animatronic Personalities

This directory contains drop-in personality folders for the animatronic system. Each personality is completely self-contained - just add or remove folders to manage personalities!

Personalities are defined using simple YAML files - **no programming required**.

## Available Personalities

> **Note on RVC voices:** entries listed "with RVC" describe the intended, voice-converted character. The RVC `.pth`/`.index` models are **not distributed with this project** (they are gitignored); you must train or obtain your own and drop them in the personality folder. Without a model, the personality falls back to the raw OpenAI TTS voice shown.

### Johnny (Tiki Bartender)
- **Wake word**: "Hey, Johnny"
- **Voice**: Shimmer with RVC (input voice; his character comes from RVC conversion)
- **Character**: Laid-back beatnik bartender with deep knowledge of tiki culture, surf music, and tropical drinks
- **Filler phrases**: Bar activities like making orgeat, grabbing mint, checking rum barrels, etc.

### Mr. Lincoln (Abraham Lincoln)
- **Wake word**: "Hey, Mr. Lincoln"
- **Voice**: Echo (male, dignified)
- **Character**: 16th President of the United States - a homage to Disney's Great Moments with Mr. Lincoln
- **Filler phrases**: Consulting documents, reviewing correspondence, reflecting on the Constitution, etc.

### Leopold (Conspiracy Theorist)
- **Wake word**: "Hey, Leopold"
- **Voice**: Onyx with RVC (male, conspiratorial)
- **Character**: Eccentric truth-seeker with an insane backstory (Turkish prison, UFO abductions, intelligence contractor)
- **Filler phrases**: Checking bug detectors, scanning perimeter, reviewing surveillance footage, etc.

### Fred (Mister Rogers)
- **Wake word**: "Hey, Fred"
- **Voice**: Echo with RVC (gentle, warm)
- **Character**: Fred Rogers from Mister Rogers' Neighborhood - speaks with gentle warmth and simple wisdom
- **Filler phrases**: Taking time to think, talking about neighbors, being kind, etc.

### K.I.T.T. (Knight Industries Two Thousand)
- **Wake word**: "Hey, Kitt"
- **Voice**: Onyx with RVC (sophisticated AI)
- **Character**: Advanced AI from the Knight Rider Trans Am - intelligent with dry wit and occasional sarcasm
- **Filler phrases**: Scanning systems, analyzing data, running diagnostics, etc.

### Jarvis (Just A Rather Very Intelligent System)
- **Wake word**: "Hey, Jarvis"
- **Voice**: Fable with RVC (refined British butler)
- **Character**: Tony Stark's AI butler - unfailingly polite and precise, with dry wit and unflappable calm authority
- **Filler phrases**: Consulting records, running diagnostics, cross-referencing databases, etc.

### Teddy Ruxpin (Storytelling Bear)
- **Wake word**: "Hey, Teddy Ruxpin"
- **Voice**: Shimmer with RVC (warm, friendly)
- **Character**: The classic 1980s storytelling teddy bear from the magical land of Grundo
- **Filler phrases**: Recalling adventures with Grubby, thinking about crystals, remembering stories, etc.

## Switching Personalities

To switch personalities, update the `PERSONALITY` setting in your `.env` file:

```bash
# Use Johnny the Tiki Bartender
PERSONALITY=johnny

# Use Mr. Lincoln
PERSONALITY=mr_lincoln

# Use Leopold the Conspiracy Theorist
PERSONALITY=leopold

# Use Fred (Mister Rogers)
PERSONALITY=fred

# Use K.I.T.T. (Knight Rider AI)
PERSONALITY=kitt

# Use Jarvis (AI butler)
PERSONALITY=jarvis

# Use Teddy Ruxpin
PERSONALITY=teddy_ruxpin
```

## Creating a New Personality

**📖 Full Guide:** For a comprehensive step-by-step tutorial, see [docs/CREATING_PERSONALITIES.md](../docs/CREATING_PERSONALITIES.md)

**Quick Start:** Creating a personality is simple - just create a folder and a YAML file!

### Step 1: Copy an Existing Personality

```bash
# Copy an existing personality as a template
cp -r personalities/johnny personalities/yourname
```

### Step 2: Edit personality.yaml

Open `personalities/yourname/personality.yaml` and customize:

```yaml
# Your personality name
name: YourName

# OpenAI TTS voice (onyx, echo, fable, nova, shimmer, or alloy)
tts_voice: onyx

# TTS speed (0.25 to 4.0, default 1.0)
# Adjust to match character energy: slower for dignified, faster for manic
tts_speed: 1.0

# TTS style instruction (optional, for gpt-4o-mini-tts model)
# Controls tone, emotional range, and speaking style
tts_style: "Speak warmly and conversationally"

# Wake word model filename (in this same directory)
wake_word_model: hey_yourname.onnx

# Optional: RVC voice conversion for custom voice models
# rvc_enabled: true
# rvc_model: yourname_voice.pth
# rvc_index_file: yourname_voice.index  # Optional
# rvc_pitch_shift: 0  # Semitones, -12 to 12
# rvc_index_rate: 0.75  # Index influence, 0.0 to 1.0
# rvc_f0_method: rmvpe  # Pitch detection method

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
- Place it in your personality's directory: `personalities/yourname/hey_yourname.onnx`

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
├── scheduled_events.yaml          # Optional — proactive greetings/reminders
└── filler_audio/                  # Device-specific pre-generated filler audio
    ├── teddy_ruxpin/              # Filler audio with PPM control signals
    │   ├── filler_01.wav
    │   ├── filler_02.wav
    │   └── ...
    ├── headless/                  # Filler audio for computer playback
    │   ├── filler_01.wav
    │   ├── filler_02.wav
    │   └── ...
    └── squawkers_mccaw/           # Filler audio for Squawkers McCaw
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
- **onyx**: Male, casual (used by Leopold and K.I.T.T.)
- **echo**: Male, dignified (used by Mr. Lincoln and Fred)
- **fable**: Male, expressive (used by Jarvis)
- **nova**: Female, friendly
- **shimmer**: Female, warm (input voice for Johnny and Teddy Ruxpin, both RVC-converted)
- **alloy**: Neutral

## Filler Phrases

Filler phrases play immediately after speech detection while the real response is being generated. They should:
- Be 8-10 seconds long
- End with a transition like "Now...", "So...", "Alright..."
- Reflect the character's activities and personality
- Give enough time for API processing (Whisper + GPT + TTS)

**Note:** When you run `python scripts/generate_fillers.py`, the system automatically generates device-specific versions of each filler phrase for all supported output devices (Teddy Ruxpin with PPM signals, Headless/Squawkers McCaw with simple stereo, etc.). The appropriate version is loaded based on your `OUTPUT_DEVICE_TYPE` setting.

## Scheduled Events (optional)

Drop a `scheduled_events.yaml` in any personality folder to make the
character speak proactively at specific times — morning greetings, bedtime
stories, holiday surprises. Events only fire when the device is IDLE, so
they never interrupt an in-progress conversation.

Schedule syntax (intentionally tiny — see `personalities/johnny/scheduled_events.yaml`
for a working example):
```yaml
quiet_hours:
  start: "22:00"
  end: "07:00"
events:
  - name: morning_greeting
    when: "08:30"            # daily
    say: "Mornin'!"
  - name: weekday_reminder
    when: "17:00 weekdays"   # mon–fri (also: "weekends", or "mon,wed,fri")
    prompt: "Remind me to wrap up work in one short sentence — stay in character."
  - name: christmas_morning
    when: "08:00 2026-12-25" # one-shot date
    say: "Merry Christmas!"
```

Each event uses either `say:` (verbatim TTS, fastest) or `prompt:` (fed to
the LLM in character, varies each time). Set `SCHEDULER_ENABLED=false` in
`.env` to globally disable. **Edits require a process restart.**

## Technical Details

### YAML Format

Personalities are defined in `personality.yaml` files with these fields:

**Required fields:**
- **`name`**: Character name shown to users
- **`tts_voice`**: OpenAI TTS voice ID (onyx, echo, fable, nova, shimmer, or alloy)
- **`wake_word_model`**: Filename of the .onnx wake word model
- **`system_prompt`**: Multi-line text defining the character's personality
- **`filler_phrases`**: List of 8-10 second phrases for low-latency response

**Optional TTS settings (for gpt-4o-mini-tts model):**
- **`tts_speed`**: Speech speed from 0.25 to 4.0 (default: 1.0). Adjust to match character energy - slower for dignified characters (0.9), faster for manic ones (1.1)
- **`tts_style`**: Style instruction to control tone, emotional range, intonation, and speaking style (e.g., "Speak warmly and casually" or "Use a dignified, authoritative tone")

**Optional RVC (voice conversion) settings:**
- **`rvc_enabled`**: Tri-state. `true` = on, `false` = off (authoritative, even if a model file is present), **omitted** = auto (on only if a model file resolves). So a personality whose folder contains a matching `.pth` turns RVC on by itself.
- **`rvc_model`**: RVC model filename (.pth). Optional: if omitted, the loader looks for `<foldername>.pth` in the personality directory (e.g. `fred/fred.pth`). An explicit value is used as-is. If nothing resolves, RVC is skipped and the raw TTS audio is used.
- **`rvc_index_file`**: Optional index file for improved quality. Same convention: if omitted, looks for `<foldername>.index`.
- **`rvc_pitch_shift`**: Pitch adjustment in semitones, -12 to +12 (default: 0)
- **`rvc_index_rate`**: Index influence, 0.0 to 1.0 (default: 0.5)
- **`rvc_f0_method`**: Pitch detection method - pm, harvest, crepe, dio, or rmvpe (default: harvest; use pm on macOS, rmvpe on Linux/Windows for best quality)
- **`rvc_filter_radius`**: Median filtering radius, 0-7 (default: 3)
- **`rvc_rms_mix_rate`**: Volume envelope mixing, 0.0-1.0 (default: 0.25)
- **`rvc_protect`**: Protect voiceless consonants, 0.0-0.5 (default: 0.33)

**Note:** RVC transforms TTS output with custom trained voice models for unique character voices beyond OpenAI TTS alone. See [docs/CREATING_PERSONALITIES.md](../docs/CREATING_PERSONALITIES.md) for detailed RVC setup guide.

**Optional Spotify settings:**
- **`spotify_enabled`**: Let this personality control Spotify playback by voice (**default: true**). Set it to `false` to exclude this character. The music tools are only offered to the model when this isn't false **and** `SPOTIFY_ENABLED=true` in `.env`. Completing the one-time login is what lets those tools actually reach Spotify (without it, a music command just returns a spoken "not set up" reply). See [docs/SPOTIFY_SETUP.md](../docs/SPOTIFY_SETUP.md).

### Auto-Discovery

The system automatically scans `personalities/` for subdirectories containing `personality.yaml` files. No manual registration needed!

### Validation

When a personality loads, the system validates:
- All required fields are present
- `filler_phrases` is a list
- Wake word model file exists
- YAML syntax is correct
