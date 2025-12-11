#!/bin/bash
# Setup script for J.F. Sebastian AI system

set -e  # Exit on error

echo "======================================================================"
echo "J.F. Sebastian - Animatronic AI Conversation System"
echo '"I make friends. They'\''re toys. My friends are toys. I make them."'
echo "======================================================================"
echo

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_step() {
    echo
    echo "[$1] $2"
    echo "----------------------------------------------------------------------"
}

# Check Python version
print_step "1/10" "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    print_error "Python 3.10+ required (found $python_version)"
    exit 1
fi
print_success "Python $python_version"

# Create virtual environment
print_step "2/10" "Creating virtual environment..."
if [ -d "venv" ]; then
    print_warning "Virtual environment already exists (skipping)"
else
    python3 -m venv venv
    print_success "Virtual environment created"
fi

# Activate virtual environment
print_step "3/10" "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_step "4/10" "Upgrading pip..."
pip install --upgrade pip -q
print_success "Pip upgraded"

# Install dependencies
print_step "5/10" "Installing Python dependencies..."
echo "This may take a few minutes..."
pip install -r requirements.txt -q
print_success "Dependencies installed"

# Download OpenWakeWord preprocessing models
print_step "6/10" "Downloading OpenWakeWord preprocessing models..."
echo "Downloading required model files (melspectrogram.onnx, embedding_model.onnx)..."
python3 -c "from openwakeword import utils; utils.download_models(['alexa'])" 2>/dev/null || {
    print_warning "OpenWakeWord models may already exist or download failed"
    echo "Checking if models exist..."
    python3 -c "
import os
from pathlib import Path
model_dir = Path('venv/lib/python*/site-packages/openwakeword/resources/models')
matches = list(Path('venv/lib').glob('python*/site-packages/openwakeword/resources/models'))
if matches:
    model_dir = matches[0]
    mel_exists = (model_dir / 'melspectrogram.onnx').exists()
    emb_exists = (model_dir / 'embedding_model.onnx').exists()
    if mel_exists and emb_exists:
        print('✓ Models already exist')
    else:
        print('⚠ Models may be missing')
        exit(1)
else:
    print('⚠ Model directory not found')
    exit(1)
" && print_success "OpenWakeWord preprocessing models ready" || print_warning "May need to download models manually"
}

# Check for system dependencies
print_step "7/10" "Checking system dependencies..."
if ! command -v brew &> /dev/null; then
    print_warning "Homebrew not found. Install manually: https://brew.sh"
    echo "  Required packages: portaudio, ffmpeg"
    echo "  On macOS: brew install portaudio ffmpeg"
else
    print_success "Homebrew found"

    if ! brew list portaudio &> /dev/null; then
        echo "Installing PortAudio..."
        brew install portaudio
    else
        print_success "PortAudio installed"
    fi

    if ! brew list ffmpeg &> /dev/null; then
        echo "Installing FFmpeg..."
        brew install ffmpeg
    else
        print_success "FFmpeg installed"
    fi
fi

# Create required directories
print_step "8/10" "Creating required directories..."
directories=("debug_audio" "models" "personalities/johnny/filler_audio" "personalities/rich/filler_audio")
for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_success "Created $dir/"
    else
        print_success "$dir/ exists"
    fi
done

# Setup configuration
print_step "9/10" "Setting up configuration..."
if [ -f ".env" ]; then
    print_warning ".env file already exists (skipping creation)"

    # Validate .env has required keys
    echo "Validating .env configuration..."
    missing_keys=()

    if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null; then
        missing_keys+=("OPENAI_API_KEY")
    fi

    if ! grep -q "PERSONALITY=" .env 2>/dev/null; then
        missing_keys+=("PERSONALITY")
    fi

    if [ ${#missing_keys[@]} -gt 0 ]; then
        print_warning "Missing or incomplete configuration keys:"
        for key in "${missing_keys[@]}"; do
            echo "    - $key"
        done
    else
        print_success "Configuration validated"
    fi
else
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success "Created .env from template"
    else
        print_error ".env.example not found!"
        exit 1
    fi
fi

# Check for wake word models
print_step "10/10" "Checking wake word models..."
models_found=0
models_missing=()

if [ -f "models/hey_johnny.onnx" ]; then
    print_success "Johnny wake word model found (hey_johnny.onnx)"
    models_found=$((models_found + 1))
else
    models_missing+=("hey_johnny.onnx (for Johnny personality)")
fi

if [ -f "models/hey_rich.onnx" ]; then
    print_success "Rich wake word model found (hey_rich.onnx)"
    models_found=$((models_found + 1))
else
    models_missing+=("hey_rich.onnx (for Rich personality)")
fi

if [ $models_found -eq 0 ]; then
    print_warning "No wake word models found in models/ directory"
    echo "You need to train custom wake word models using OpenWakeWord."
    echo "See: https://github.com/dscripka/openWakeWord for training instructions"
else
    print_success "Found $models_found wake word model(s)"
fi

if [ ${#models_missing[@]} -gt 0 ]; then
    echo
    print_warning "Missing wake word models:"
    for model in "${models_missing[@]}"; do
        echo "    - $model"
    done
fi

# List audio devices
echo
echo "======================================================================"
echo "Listing available audio devices..."
echo "======================================================================"
python -m teddy_ruxpin.modules.audio_output 2>/dev/null || print_warning "Could not list audio devices"

# Final instructions
echo
echo "======================================================================"
echo "Setup Complete!"
echo "======================================================================"
echo

# Check what needs to be done
needs_config=false
needs_models=false
needs_fillers=false

if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null; then
    needs_config=true
fi

if [ $models_found -eq 0 ]; then
    needs_models=true
fi

# Check if filler phrases exist
if [ ! -f "personalities/johnny/filler_audio/filler_01.wav" ]; then
    needs_fillers=true
fi

echo "Next steps:"
echo

if [ "$needs_config" = true ]; then
    echo "1. ${YELLOW}REQUIRED${NC}: Edit .env and add your OpenAI API key"
    echo "   - Get key from: https://platform.openai.com/api-keys"
    echo "   - Set: OPENAI_API_KEY=sk-your-key-here"
    echo
fi

echo "2. Configure audio devices in .env (see device list above):"
echo "   INPUT_DEVICE_NAME=\"MacBook Air Microphone\""
echo "   OUTPUT_DEVICE_NAME=\"Arsvita\""
echo

if [ "$needs_models" = true ]; then
    echo "3. ${YELLOW}REQUIRED${NC}: Add wake word models to models/ directory"
    echo "   - Train custom models: https://github.com/dscripka/openWakeWord"
    echo "   - Place .onnx files in models/"
    echo "     • models/hey_johnny.onnx (for Johnny personality)"
    echo "     • models/hey_rich.onnx (for Rich personality)"
    echo
fi

if [ "$needs_fillers" = true ]; then
    echo "4. Generate filler phrases:"
    echo "   python scripts/generate_fillers.py"
    echo
fi

echo "5. Run the application:"
echo "   python3 -m teddy_ruxpin.main"
echo

echo "For detailed documentation:"
echo "  - README.md - Complete guide and setup instructions"
echo "  - personalities/README.md - How to create personalities"
echo

if [ "$needs_config" = true ] || [ "$needs_models" = true ]; then
    print_warning "Setup incomplete - please complete required steps above"
else
    print_success "Setup complete! You're ready to run the application."
fi

echo
