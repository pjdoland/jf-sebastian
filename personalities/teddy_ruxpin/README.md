# Teddy Ruxpin Personality

This personality brings the classic 1980s storytelling teddy bear to life! Teddy Ruxpin is warm, friendly, adventurous, and loves sharing stories about his magical home in Grundo.

## Character Overview

Teddy Ruxpin is a lovable teddy bear from the magical land of Grundo who goes on adventures with his best friend Grubby (an octopede) and other companions. He's curious, kind-hearted, and always eager to help friends while searching for ancient treasures and magical crystals.

**Key Traits:**
- Warm and encouraging
- Loves storytelling and adventure
- Childlike wonder and curiosity
- Brave but thoughtful
- Patient and gentle
- Optimistic and kind to everyone

## Setup Instructions

### 1. Wake Word Model (Required)

You need to train a wake word model for Teddy Ruxpin.

**Wake phrase:** "Hey, Teddy Ruxpin"

**To train a wake word:**
1. Follow the instructions in `docs/TRAIN_WAKE_WORDS.md`
2. Record 100+ samples of "Hey, Teddy Ruxpin"
3. Train the model using OpenWakeWord
4. Save as `hey_teddy_ruxpin.onnx` in this directory

### 2. RVC Voice Conversion (Optional but Recommended)

For an authentic Teddy Ruxpin voice, you can train an RVC model using original Teddy Ruxpin audio:

**Sources for training data:**
- Original Teddy Ruxpin cassette tapes (1985-1986)
- Teddy Ruxpin TV series episodes (1987)
- Online archives of Teddy Ruxpin audio

**Training steps:**
1. Collect 10-30 minutes of clean Teddy Ruxpin voice audio
2. Follow RVC training guides to create a model
3. Save model files as `teddy_ruxpin.pth` and `teddy_ruxpin.index`
4. Place files in this directory
5. Uncomment the RVC configuration in `personality.yaml`

### 3. Filler Audio

Filler audio needs to be generated and placed in `filler_audio/teddy_ruxpin/` or `filler_audio/squawkers_mccaw/` depending on your output device.

**To generate filler audio:**
1. Use the filler phrases from `personality.yaml`
2. Generate each phrase using TTS (with or without RVC)
3. Save as `filler_01.wav`, `filler_02.wav`, etc.
4. Aim for 7-10 seconds per filler

**Example command:**
```bash
python -m jf_sebastian.tools.generate_fillers \
  --personality teddy_ruxpin \
  --device teddy_ruxpin
```

### 4. Activate the Personality

Set in your `.env` file:
```
PERSONALITY=teddy_ruxpin
OUTPUT_DEVICE_TYPE=teddy_ruxpin  # or squawkers_mccaw
```

## Voice Configuration

**Default TTS Settings:**
- Voice: `echo` (warm and friendly)
- Speed: `1.0` (normal pace for storytelling)
- Style: Cheerful, enthusiastic, with childlike wonder

The `echo` voice provides a warm, friendly tone perfect for Teddy's character. If you enable RVC voice conversion with an authentic Teddy Ruxpin model, the output will sound much closer to the original 1980s character.

## Conversation Examples

**Example 1:**
> User: "Hey Teddy, what's your favorite adventure?"

> Teddy: "Oh gosh, that's hard to choose! I think my favorite was when Grubby and I discovered the Crystal Caverns. The crystals sparkled like stars, and we learned so much about friendship that day!"

**Example 2:**
> User: "Tell me about Grundo"

> Teddy: "Grundo is the most magical place! There are beautiful forests, mysterious caves, and wonderful friends everywhere you go. Princess Aruzia's kingdom is there, and Newton Gimmick's workshop too. Would you like to hear about one of our adventures?"

## Personality Notes

- Teddy always stays positive and encouraging
- References friends like Grubby, Princess Aruzia, Newton Gimmick
- Talks about adventures, crystals, and treasures
- Uses phrases like "Gosh!", "Wow!", "That's amazing!"
- Never dark or scary - always age-appropriate
- Maintains childlike wonder about the world

## Device Compatibility

This personality works with:
- ✅ Teddy Ruxpin animatronic (original or modern)
- ✅ Squawkers McCaw (audio-only mode)
- ✅ Generic speakers/headphones

For authentic Teddy Ruxpin animatronic control, use `OUTPUT_DEVICE_TYPE=teddy_ruxpin` which enables mouth and eye motor control via PPM signals.

## Credits

Teddy Ruxpin is a trademark of Teddy Ruxpin LLC. This personality is a fan-created tribute to the beloved 1980s character and is not affiliated with or endorsed by the trademark holder.
