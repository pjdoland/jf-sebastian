# Training Custom Wake Words with OpenWakeWord

This guide explains how to train custom wake word models for your personalities using OpenWakeWord.

## Why OpenWakeWord?

- **Free & Open Source**: No API keys or subscription fees
- **Easy Custom Training**: Train models for any phrase you want
- **Flexible**: Works with any wake phrase
- **No Vendor Lock-in**: Models are yours to keep and modify

## Prerequisites

- Python 3.8+
- A quiet recording environment
- A good microphone
- 10-20 minutes of time

## Training Process

### 1. Install OpenWakeWord Training Tools

```bash
pip install openwakeword[training]
```

### 2. Record Your Wake Phrase

You'll need to record yourself saying the wake phrase (e.g., "Hey Johnny" or "Hey Rich") multiple times in different ways:

- Different tones (normal, excited, tired)
- Different volumes (quiet, normal, loud)
- Different speeds (fast, normal, slow)
- At least 50-100 samples recommended

### 3. Record Negative Samples

Record yourself saying similar but different phrases to help the model distinguish:

- "Hey John" (without the "ny")
- "Johnny" (without the "Hey")
- Other common phrases that might sound similar

### 4. Train the Model

Use OpenWakeWord's training scripts:

```bash
# Follow the OpenWakeWord documentation at:
# https://github.com/dscripka/openWakeWord

# Example training command (adjust paths):
python train.py \
  --positive_dir ./recordings/hey_johnny/positive \
  --negative_dir ./recordings/hey_johnny/negative \
  --output models/hey_johnny.onnx
```

### 5. Place Model in Project

Move your trained `.onnx` file to the `models/` directory:

```bash
mv hey_johnny.onnx /path/to/jf-sebastian/models/
mv hey_rich.onnx /path/to/jf-sebastian/models/
```

### 6. Update Personality Configuration

The personality files already reference the model paths:

- Johnny: `models/hey_johnny.onnx`
- Rich: `models/hey_rich.onnx`

No code changes needed - just place your models in the right location!

## Using Pre-trained Models

OpenWakeWord comes with several pre-trained models you can use for testing:

- "hey_jarvis"
- "alexa"
- "hey_mycroft"
- "hey_rhasspy"

To use a pre-trained model, update the personality file to reference the bundled model.

## Tips for Good Models

1. **Variety**: Record in different rooms, at different times of day
2. **Natural Speech**: Say the phrase naturally, not robotic
3. **Background Noise**: Include some samples with typical background noise
4. **Multiple Speakers**: If multiple people will use it, have them record samples
5. **Test Iteratively**: Start with a basic model, test it, collect more samples of failures, retrain

## Troubleshooting

### Model not detecting wake word
- Train with more samples
- Adjust detection threshold in `wake_word.py` (line 191, currently 0.5)
- Ensure you're speaking clearly and at a normal volume

### Too many false positives
- Add more negative samples during training
- Increase detection threshold
- Make sure negative samples include similar-sounding phrases

### Model file too large
- Use ONNX format (smaller than other formats)
- Consider quantization if supported

## Resources

- [OpenWakeWord GitHub](https://github.com/dscripka/openWakeWord)
- [OpenWakeWord Documentation](https://github.com/dscripka/openWakeWord/tree/main/docs)
- [Training Tutorial](https://github.com/dscripka/openWakeWord/blob/main/docs/training.md)

## Notes

- Training requires more dependencies than runtime (add `[training]` to pip install)
- Model training can take 30 minutes to several hours depending on samples and hardware
- You can use Google Colab for training if you don't have a powerful local machine
- Models are specific to the phrase - you need separate models for "Hey Johnny" and "Hey Rich"
