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

# Find or install Python 3.10
print_step "1/12" "Finding Python 3.10..."

# Function to check if a Python command is version 3.10
check_python_310() {
    local python_cmd=$1
    if command -v "$python_cmd" &> /dev/null; then
        local version=$($python_cmd --version 2>&1 | awk '{print $2}')
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" = "3" ] && [ "$minor" = "10" ]; then
            echo "$python_cmd"
            return 0
        fi
    fi
    return 1
}

# Try to find Python 3.10
PYTHON_CMD=""
if PYTHON_CMD=$(check_python_310 "python3"); then
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    print_success "Found Python $python_version (default python3)"
elif PYTHON_CMD=$(check_python_310 "python3.10"); then
    python_version=$(python3.10 --version 2>&1 | awk '{print $2}')
    print_success "Found Python $python_version (python3.10)"
else
    # Python 3.10 not found - offer to install
    current_version=$(python3 --version 2>&1 | awk '{print $2}' || echo "none")
    print_warning "Python 3.10 not found (current: $current_version)"
    echo "RVC requires Python 3.10.x specifically (not 3.11+)"
    echo ""

    # Check for pyenv first (preferred method)
    if command -v pyenv &> /dev/null; then
        echo "Found pyenv - can install Python 3.10 automatically"
        read -p "Install Python 3.10 via pyenv? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Installing Python 3.10.13 via pyenv..."
            pyenv install 3.10.13 -s
            pyenv local 3.10.13
            PYTHON_CMD="python3"
            print_success "Installed Python 3.10.13 via pyenv"
        else
            print_error "Setup cancelled - Python 3.10 required"
            exit 1
        fi
    # Check for Homebrew (macOS)
    elif command -v brew &> /dev/null; then
        echo "Found Homebrew - can install Python 3.10 automatically"
        read -p "Install Python 3.10 via Homebrew? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Installing Python 3.10 via Homebrew..."
            brew install python@3.10
            PYTHON_CMD="python3.10"
            print_success "Installed Python 3.10 via Homebrew"
        else
            print_error "Setup cancelled - Python 3.10 required"
            exit 1
        fi
    else
        print_error "No package manager found (pyenv or brew)"
        echo "Please install Python 3.10 manually:"
        echo "  - Via pyenv: https://github.com/pyenv/pyenv"
        echo "  - Via Homebrew: brew install python@3.10"
        echo "  - Direct download: https://www.python.org/downloads/"
        exit 1
    fi
fi

# Create virtual environment
print_step "2/12" "Creating virtual environment..."
if [ -d "venv" ]; then
    # Check if existing venv uses Python 3.10
    venv_python_version=$(venv/bin/python --version 2>&1 | awk '{print $2}')
    venv_major=$(echo "$venv_python_version" | cut -d. -f1)
    venv_minor=$(echo "$venv_python_version" | cut -d. -f2)

    if [ "$venv_major" = "3" ] && [ "$venv_minor" = "10" ]; then
        print_success "Virtual environment exists (Python $venv_python_version)"
    else
        print_warning "Existing venv uses Python $venv_python_version (need 3.10.x)"
        read -p "Recreate venv with Python 3.10? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo "Removing old virtual environment..."
            rm -rf venv
            $PYTHON_CMD -m venv venv
            print_success "Virtual environment recreated with Python 3.10"
        else
            print_error "Setup cancelled - Python 3.10 venv required for RVC"
            exit 1
        fi
    fi
else
    $PYTHON_CMD -m venv venv
    print_success "Virtual environment created with $PYTHON_CMD"
fi

# Activate virtual environment
print_step "3/12" "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_step "4/12" "Upgrading pip..."
pip install --upgrade pip -q
print_success "Pip upgraded"

# Install dependencies
print_step "5/12" "Installing Python dependencies..."
echo "This may take a few minutes..."
pip install -r requirements.txt -q
print_success "Dependencies installed"

# Install RVC (optional)
print_step "6/12" "Installing RVC voice conversion (optional)..."
echo "RVC enables custom trained voice models beyond OpenAI TTS voices."
echo "This requires temporarily downgrading pip and takes 5-10 minutes."
echo "The system works perfectly without RVC (using OpenAI TTS only)."
echo ""
read -p "Install RVC dependencies? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing RVC..."

    # Get current pip version
    current_pip=$(pip --version | awk '{print $2}')
    echo "Current pip version: $current_pip"

    # Downgrade pip for compatibility
    echo "Downgrading pip to 24.0 for compatibility..."
    pip install pip==24.0 -q
    print_success "Pip downgraded to 24.0"

    # Install RVC dependencies
    echo "Installing RVC dependencies (torch, fairseq, rvc-python)..."
    echo "This may take 5-10 minutes..."
    pip install -r requirements-rvc.txt -q
    print_success "RVC dependencies installed"

    # Upgrade pip back
    echo "Upgrading pip back to latest..."
    pip install --upgrade pip -q
    new_pip=$(pip --version | awk '{print $2}')
    print_success "Pip upgraded to $new_pip"

    # Test RVC availability
    echo "Testing RVC availability..."
    python -c "
try:
    from rvc_python.infer import RVCInference
    print('✓ rvc-python is available')
    print('✓ RVC voice conversion is ready to use')
except ImportError as e:
    print('✗ RVC import failed:', e)
    exit(1)
" || {
        print_warning "RVC installed but import test failed"
        echo "You may need to reinstall: ./scripts/install_rvc.sh"
    }
    print_success "RVC installation complete"
else
    print_warning "Skipped RVC installation"
    echo "You can install later with: ./scripts/install_rvc.sh"
fi

# Download OpenWakeWord preprocessing models
print_step "7/12" "Downloading OpenWakeWord preprocessing models..."
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
print_step "8/12" "Checking system dependencies..."
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
print_step "9/12" "Creating required directories..."
directories=("debug_audio" "personalities/johnny/filler_audio" "personalities/mr_lincoln/filler_audio" "personalities/leopold/filler_audio")
for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_success "Created $dir/"
    else
        print_success "$dir/ exists"
    fi
done

# Setup configuration
print_step "10/12" "Setting up configuration..."
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

# Generate filler audio for all personalities (optional)
print_step "11/12" "Generating filler audio for personalities..."
echo "This creates pre-recorded phrases that play immediately while processing responses."
echo "This is optional and takes 2-3 minutes."
echo ""
read -p "Generate filler audio now? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Generating for all personalities..."
    python scripts/generate_fillers.py 2>&1 | grep -E "(Processing:|Saved:|complete)" || {
        print_warning "Filler generation failed or incomplete"
        echo "You can generate manually later with: python scripts/generate_fillers.py"
    }
    print_success "Filler audio generated"
else
    print_warning "Skipped filler audio generation"
    echo "You can generate later with: python scripts/generate_fillers.py"
fi

# Check for wake word models
print_step "12/12" "Checking wake word models..."
models_found=0
models_missing=()

# Check for personality wake word models in their directories
for personality in johnny mr_lincoln leopold; do
    if [ -f "personalities/$personality/hey_$personality.onnx" ]; then
        print_success "$personality wake word model found"
        models_found=$((models_found + 1))
    else
        models_missing+=("hey_$personality.onnx (for $personality personality)")
    fi
done

if [ $models_found -eq 0 ]; then
    print_warning "No wake word models found"
    echo "Wake word models should be in each personality's directory."
    echo "See docs/TRAIN_WAKE_WORDS.md for training instructions"
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
python -m jf_sebastian.modules.audio_output 2>/dev/null || print_warning "Could not list audio devices"

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

echo "Next steps:"
echo

step_num=1

if [ "$needs_config" = true ]; then
    echo "${step_num}. ${YELLOW}REQUIRED${NC}: Edit .env and add your OpenAI API key"
    echo "   - Get key from: https://platform.openai.com/api-keys"
    echo "   - Set: OPENAI_API_KEY=sk-your-key-here"
    echo
    step_num=$((step_num + 1))
fi

echo "${step_num}. Configure audio devices in .env (see device list above):"
echo "   INPUT_DEVICE_NAME=\"MacBook Air Microphone\""
echo "   OUTPUT_DEVICE_NAME=\"Arsvita\""
echo
step_num=$((step_num + 1))

if [ "$needs_models" = true ]; then
    echo "${step_num}. ${YELLOW}NOTE${NC}: Some wake word models may be missing"
    echo "   - All personalities have wake word models in their directories"
    echo "   - See docs/TRAIN_WAKE_WORDS.md to create custom wake words"
    echo
    step_num=$((step_num + 1))
fi

echo "${step_num}. Run the application:"
echo "   ./run.sh"
echo "   or: python3 -m jf_sebastian.main"
echo

echo "For detailed documentation:"
echo "  - README.md - Complete guide and setup instructions"
echo "  - docs/CREATING_PERSONALITIES.md - RVC configuration guide"
echo "  - personalities/README.md - How to create personalities"
echo

if [ "$needs_config" = true ] || [ "$needs_models" = true ]; then
    print_warning "Setup incomplete - please complete required steps above"
else
    print_success "Setup complete! You're ready to run the application."
fi

echo
