#!/bin/bash
# Setup script for J.F. Sebastian AI system

echo "======================================================================"
echo "J.F. Sebastian - Animatronic AI Conversation System"
echo '"I make friends. They'\''re toys. My friends are toys. I make them."'
echo "======================================================================"
echo

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10+ required (found $python_version)"
    exit 1
fi
echo "✓ Python $python_version"
echo

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists"
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo

# Check for system dependencies
echo "Checking system dependencies..."
if ! command -v brew &> /dev/null; then
    echo "⚠ Homebrew not found. You may need to install PortAudio and FFmpeg manually."
    echo "  On macOS: brew install portaudio ffmpeg"
else
    echo "Homebrew found. Checking for required packages..."

    if ! brew list portaudio &> /dev/null; then
        echo "Installing PortAudio..."
        brew install portaudio
    else
        echo "✓ PortAudio installed"
    fi

    if ! brew list ffmpeg &> /dev/null; then
        echo "Installing FFmpeg..."
        brew install ffmpeg
    else
        echo "✓ FFmpeg installed"
    fi
fi
echo

# Setup configuration
echo "Setting up configuration..."
if [ -f ".env" ]; then
    echo "⚠ .env file already exists. Skipping..."
else
    cp .env.example .env
    echo "✓ Created .env file from template"
    echo
    echo "IMPORTANT: Edit .env and add your API keys:"
    echo "  - OPENAI_API_KEY (from https://platform.openai.com/api-keys)"
    echo "  - PICOVOICE_ACCESS_KEY (from https://console.picovoice.ai/)"
fi
echo

# Create debug directory
echo "Creating debug directories..."
mkdir -p debug_audio
echo "✓ Debug directories created"
echo

# List audio devices
echo "Listing available audio devices..."
python -m teddy_ruxpin.modules.audio_output
echo

# Final instructions
echo "======================================================================"
echo "Setup Complete!"
echo "======================================================================"
echo
echo "Next steps:"
echo "1. Edit .env and add your API keys"
echo "2. Choose personality: Set PERSONALITY=johnny or PERSONALITY=rich in .env"
echo "3. Configure audio devices in .env (device names recommended):"
echo "   INPUT_DEVICE_NAME=\"MacBook Air Microphone\""
echo "   OUTPUT_DEVICE_NAME=\"Arsvita\""
echo "   (See device list above for available devices)"
echo "4. Generate filler phrases: python scripts/generate_fillers.py --personality johnny"
echo "5. Run: ./run.sh"
echo
echo "For detailed instructions, see QUICKSTART.md"
echo "To learn about the project, see README.md and ABOUT.md"
echo
