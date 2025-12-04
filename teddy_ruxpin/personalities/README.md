# Animatronic Personalities

This directory contains modular personality definitions for the animatronic bear system. Each personality has its own wake word, system prompt, filler phrases, and voice.

## Available Personalities

### Johnny (Tiki Bartender)
- **Wake word**: "Hey, Johnny"
- **Voice**: Onyx (male, casual)
- **Character**: Laid-back tiki bartender with deep knowledge of tiki culture, surf music, and tropical drinks
- **Filler phrases**: Bar activities like making orgeat, grabbing mint, checking rum barrels, etc.

### Rich (Banking CEO)
- **Wake word**: "Hey, Rich" (requires wake word file generation)
- **Voice**: Echo (male, professional)
- **Character**: Richard Bearbank, CEO of Bear Capital Bank - data-driven, strategic, approachable banking expert
- **Filler phrases**: Business activities like checking market data, reviewing portfolios, analyzing metrics, etc.

## Switching Personalities

To switch personalities, update the `PERSONALITY` setting in your `.env` file:

```bash
# Use Johnny the Tiki Bartender
PERSONALITY=johnny

# Use Rich the Banking CEO
PERSONALITY=rich
```

## Creating a New Personality

1. **Create personality directory**:
   ```bash
   mkdir -p teddy_ruxpin/personalities/yourname
   ```

2. **Create personality module** (`yourname/personality.py`):
   ```python
   from pathlib import Path
   from teddy_ruxpin.personalities.base import Personality

   class YourNamePersonality(Personality):
       @property
       def name(self) -> str:
           return "YourName"

       @property
       def system_prompt(self) -> str:
           return """Your personality description here..."""

       @property
       def wake_word_path(self) -> Path:
           return Path("/path/to/your/wake_word.ppn")

       @property
       def tts_voice(self) -> str:
           return "onyx"  # or "echo", "fable", "nova", "shimmer", "alloy"

       @property
       def filler_phrases(self) -> list[str]:
           return [
               "Your filler phrase 1...",
               "Your filler phrase 2...",
               # ... 30 total phrases recommended
           ]
   ```

3. **Create package init** (`yourname/__init__.py`):
   ```python
   from .personality import YourNamePersonality
   __all__ = ['YourNamePersonality']
   ```

4. **Register in personality system** (`teddy_ruxpin/personalities/__init__.py`):
   ```python
   from .yourname import YourNamePersonality

   PERSONALITIES = {
       "johnny": JohnnyPersonality,
       "rich": RichPersonality,
       "yourname": YourNamePersonality,  # Add this line
   }
   ```

5. **Generate custom wake word**:
   - Go to [Picovoice Console](https://console.picovoice.ai/)
   - Create a new wake word (e.g., "Hey YourName")
   - Download the `.ppn` file
   - Place in `models/` directory
   - Update `wake_word_path` in your personality

6. **Generate filler audio**:
   ```bash
   # Update scripts/generate_fillers.py to use your personality
   python scripts/generate_fillers.py
   ```

## Personality Structure

Each personality directory contains:
```
yourname/
├── __init__.py                    # Package init
├── personality.py                  # Personality definition
└── filler_audio/                  # Pre-generated filler audio
    ├── filler_01.wav
    ├── filler_02.wav
    └── ...
```

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

## Architecture

The personality system uses an abstract base class (`Personality`) that defines the interface all personalities must implement:

- `name`: Character name
- `system_prompt`: LLM personality definition
- `wake_word_path`: Path to custom wake word file
- `tts_voice`: OpenAI TTS voice ID
- `filler_phrases`: List of filler phrases
- `filler_audio_dir`: Directory for pre-generated audio (auto-generated)
