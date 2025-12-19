# J.F. Sebastian Test Suite

Comprehensive unit tests for the J.F. Sebastian animatronic AI conversation system.

## Test Structure

```
tests/
├── conftest.py              # Shared pytest fixtures
├── test_main.py             # Main application and state machine tests
├── devices/                 # Output device tests
│   ├── test_factory.py            # Device registry and factory tests
│   ├── test_audio_processor.py    # Shared audio processor tests
│   ├── test_sentiment_analyzer.py # Shared sentiment analyzer tests
│   ├── test_teddy_ruxpin.py       # Teddy Ruxpin device tests
│   └── test_squawkers_mccaw.py    # Squawkers McCaw device tests
├── modules/
│   ├── test_ppm_generator.py      # PPM signal generation tests
│   ├── test_filler_phrases.py     # Filler phrase management tests
│   ├── test_audio_input.py        # Audio input tests
│   └── test_audio_output.py       # Audio output tests
├── personalities/
│   └── test_personalities.py      # Personality system tests
└── utils/
    └── test_audio_device_utils.py # Audio device utility tests
```

## Running Tests

### Install Test Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install test dependencies
pip install pytest pytest-mock pytest-cov
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
# Test PPM generator
pytest tests/modules/test_ppm_generator.py

# Test personalities
pytest tests/personalities/test_personalities.py

# Test main application
pytest tests/test_main.py
```

### Run Tests with Coverage

```bash
# Generate coverage report
pytest --cov=jf_sebastian --cov-report=html --cov-report=term-missing

# View HTML report
open htmlcov/index.html
```

### Run Tests by Marker

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run only audio tests
pytest -m audio
```

### Verbose Output

```bash
# Show detailed test output
pytest -v

# Show print statements
pytest -s

# Show detailed failures
pytest -vv
```

## Test Coverage

The test suite covers:

### Output Devices
- **Device Factory** (test_factory.py)
  - Device registration and listing
  - Device creation by type
  - Case-insensitive device names
  - Invalid device error handling
  - Interface validation

- **Audio Processor** (test_audio_processor.py)
  - MP3 to PCM conversion
  - Custom sample rates
  - FFmpeg error handling
  - Default settings usage

- **Sentiment Analyzer** (test_sentiment_analyzer.py)
  - Positive/negative/neutral sentiment detection
  - Edge cases (empty strings, special characters)
  - Score range validation

- **Teddy Ruxpin Device** (test_teddy_ruxpin.py)
  - Device initialization and properties
  - Settings validation
  - PPM signal generation
  - Stereo output creation
  - Gain application
  - Error handling

- **Squawkers McCaw Device** (test_squawkers_mccaw.py)
  - Device initialization
  - Simple stereo output
  - Channel duplication
  - No PPM requirement validation

### Core Functionality
- **PPM Generation** (test_ppm_generator.py)
  - Signal generation with channel values
  - Audio to channel value conversion
  - Syllable-based mouth movements
  - Eye control and sentiment effects
  - Timing accuracy

- **Filler Phrase Management** (test_filler_phrases.py)
  - Filler file loading
  - Random filler selection
  - File/phrase count validation
  - Directory handling

- **Audio I/O** (test_audio_input.py, test_audio_output.py)
  - Device initialization by name/index
  - Recording start/stop
  - Audio playback (WAV files, stereo arrays)
  - Retry logic for PortAudio errors
  - Cleanup and resource management

### System Integration
- **Main Application** (test_main.py)
  - State machine transitions (IDLE → LISTENING → PROCESSING → SPEAKING)
  - Filler selection timing (before state transition)
  - Module initialization and cleanup
  - Personality loading
  - Context manager support

- **Personality System** (test_personalities.py)
  - Personality loading by name
  - Property validation (name, system_prompt, voice, etc.)
  - Filler phrase validation
  - Wake word path validation
  - Personality differentiation

- **Utilities** (test_audio_device_utils.py)
  - Device name to index resolution
  - Case-insensitive matching
  - Partial name matching
  - Device type filtering
  - Error handling

## Test Fixtures

Common fixtures are defined in `conftest.py`:

- `sample_audio`: Generate test audio waveforms
- `mock_pyaudio`: Mock PyAudio instance with device info
- `mock_openai_client`: Mock OpenAI API client
- `mock_openwakeword`: Mock OpenWakeWord detector
- `temp_audio_dir`: Temporary directory for test files
- `sample_ppm_channel_values`: Sample PPM channel data
- `mock_personality`: Mock personality instance
- `mock_settings`: Mock settings configuration

## Writing New Tests

### Example Test Structure

```python
import pytest
from unittest.mock import Mock, patch
from jf_sebastian.modules.your_module import YourClass

def test_basic_functionality():
    """Test basic functionality of YourClass."""
    obj = YourClass()
    result = obj.do_something()
    assert result is not None

@patch('jf_sebastian.modules.your_module.external_dependency')
def test_with_mock(mock_dependency):
    """Test with mocked external dependency."""
    mock_dependency.return_value = "mocked_value"
    obj = YourClass()
    result = obj.use_dependency()
    assert result == "mocked_value"
    mock_dependency.assert_called_once()

def test_error_handling():
    """Test error handling."""
    obj = YourClass()
    with pytest.raises(ValueError):
        obj.invalid_operation()
```

### Using Fixtures

```python
def test_with_fixture(sample_audio, mock_pyaudio):
    """Test using shared fixtures."""
    audio, sample_rate = sample_audio
    assert len(audio) > 0
    assert sample_rate == 16000
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines without requiring:
- Physical audio hardware
- OpenAI API keys (mocked)
- OpenWakeWord models (mocked)
- Network connectivity

All external dependencies are mocked for fast, reliable testing.

## Troubleshooting

### Import Errors

If you get import errors, ensure the project root is in PYTHONPATH:

```bash
export PYTHONPATH="${PYTHONPATH}:${PWD}"
pytest
```

### Audio Device Tests Failing

Audio device tests use mocks by default. If testing with real hardware:

```bash
# Ensure audio devices are available
python scripts/test_microphone.py
python scripts/list_audio_devices.py
```

### Slow Tests

Some tests (especially PPM generation with long audio) can be slow. Skip them:

```bash
pytest -m "not slow"
```

## Contributing

When adding new functionality:

1. Write tests first (TDD approach)
2. Ensure all tests pass: `pytest`
3. Check coverage: `pytest --cov=jf_sebastian`
4. Aim for >80% coverage on new code
5. Document complex test scenarios

## Test Markers

Available markers (defined in pytest.ini):

- `@pytest.mark.slow` - Tests that take >1 second
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.audio` - Tests involving audio I/O
- `@pytest.mark.hardware` - Tests requiring physical hardware
