#!/bin/bash
# RVC Installation Script
# Installs RVC voice conversion dependencies with pip compatibility workaround

set -e  # Exit on error

echo "======================================================================"
echo "RVC Voice Conversion Installation"
echo "======================================================================"
echo ""
echo "This script installs RVC (Retrieval-based Voice Conversion) for"
echo "custom voice models. RVC is OPTIONAL - the system works perfectly"
echo "with OpenAI TTS voices alone."
echo ""

# Check if venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Virtual environment not activated!"
    echo "Please run: source venv/bin/activate"
    exit 1
fi

# Check Python version - RVC requires 3.10 specifically
python_version=$(python3 --version 2>&1 | awk '{print $2}')
python_major=$(echo "$python_version" | cut -d. -f1)
python_minor=$(echo "$python_version" | cut -d. -f2)

if [ "$python_major" != "3" ] || [ "$python_minor" != "10" ]; then
    echo "Error: Python 3.10.x required for RVC (found $python_version)"
    echo "Python 3.11+ is not compatible with RVC dependencies"
    echo "Please recreate your virtual environment with Python 3.10"
    exit 1
fi
echo "✓ Python version: $python_version"
echo ""

# Detect Jetson (aarch64 with NVIDIA Tegra)
IS_JETSON=false
if [ "$(uname -m)" = "aarch64" ] && [ -f "/etc/nv_tegra_release" ]; then
    IS_JETSON=true
    echo "⚠ NVIDIA Jetson detected - using Jetson-specific installation"
    echo "  RVC on Jetson is EXPERIMENTAL"
    echo ""
fi

# Get current pip version
current_pip=$(pip --version | awk '{print $2}')
echo "Current pip version: $current_pip"
echo ""

# Ask for confirmation
if [ "$IS_JETSON" = true ]; then
    read -p "Install RVC dependencies? (y/N): " -n 1 -r
else
    echo "Known issue: RVC has complex dependencies requiring pip downgrade."
    read -p "Install RVC dependencies? This will temporarily downgrade pip. (y/N): " -n 1 -r
fi
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""

if [ "$IS_JETSON" = true ]; then
    # Jetson path: no pip downgrade needed, use Jetson AI Lab wheel index
    # Detect CUDA version for correct index
    if command -v nvcc &> /dev/null; then
        CUDA_VERSION=$(nvcc --version | sed -n 's/.*release \([0-9]*\.[0-9]*\).*/\1/p')
        CUDA_TAG="cu$(echo "$CUDA_VERSION" | tr -d '.')"
        echo "Detected CUDA $CUDA_VERSION"
    else
        echo "⚠ nvcc not found, defaulting to CUDA 12.6 (JetPack 6.1+)"
        CUDA_TAG="cu126"
    fi
    JETSON_INDEX="https://pypi.jetson-ai-lab.io/jp6/${CUDA_TAG}/"
    echo "Using Jetson wheel index: $JETSON_INDEX"
    echo ""

    echo "Step 1: Installing PyTorch from Jetson AI Lab index..."
    echo "This may take 10-15 minutes on Jetson..."
    pip install torch torchaudio --index-url "$JETSON_INDEX" || {
        echo "⚠ torchaudio install failed (no Jetson wheel available)"
        echo "  Installing torch only..."
        pip install torch --index-url "$JETSON_INDEX"
    }
    echo "✓ PyTorch installed from Jetson AI Lab index"
    echo ""

    echo "Step 2: Downgrading pip to 24.0 for RVC dependency resolution..."
    pip install pip==24.0 -q
    echo "✓ Pip downgraded to 24.0"
    echo ""

    echo "Step 3: Installing RVC dependencies (Jetson)..."
    echo "Some packages may compile from source - this can take 15-30 minutes..."
    pip install -r requirements-rvc-jetson.txt
    echo "✓ RVC dependencies installed"
    echo ""

    echo "Step 4: Upgrading pip back to latest..."
    pip install --upgrade pip -q
    new_pip=$(pip --version | awk '{print $2}')
    echo "✓ Pip upgraded to $new_pip"
else
    # Standard path: pip downgrade needed for fairseq dependency resolution
    echo "Step 1: Downgrading pip to 24.0 for compatibility..."
    pip install pip==24.0 -q
    echo "✓ Pip downgraded to 24.0"
    echo ""

    echo "Step 2: Installing RVC dependencies..."
    echo "This may take 5-10 minutes (torch, fairseq, rvc-python)..."
    pip install -r requirements-rvc.txt -q
    echo "✓ RVC dependencies installed"
    echo ""

    echo "Step 3: Upgrading pip back to latest..."
    read -p "Upgrade pip back to latest version? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Keeping pip at 24.0"
    else
        pip install --upgrade pip -q
        new_pip=$(pip --version | awk '{print $2}')
        echo "✓ Pip upgraded to $new_pip"
    fi
fi

echo ""
echo "======================================================================"
echo "RVC Installation Complete!"
echo "======================================================================"
echo ""
echo "Testing RVC availability..."
python3 -c "
try:
    from rvc_python.infer import RVCInference
    print('✓ rvc-python is available')
    print('✓ RVC voice conversion is ready to use')
except ImportError as e:
    print('✗ RVC import failed:', e)
    exit(1)
"

echo ""
echo "Next steps:"
echo "1. Set RVC_ENABLED=true in .env (if not already set)"
echo "2. Add RVC models to personality directories"
echo "3. Configure RVC in personality.yaml files"
echo ""
echo "See docs/CREATING_PERSONALITIES.md for RVC configuration guide."
echo ""
