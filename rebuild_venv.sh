#!/bin/bash
# Script to rebuild virtual environment from scratch

set -e  # Exit on error

echo "=================================================="
echo "Virtual Environment Rebuild Script"
echo "=================================================="
echo ""

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "Error: requirements.txt not found!"
    exit 1
fi

# Backup current venv if it exists
if [ -d "venv" ]; then
    echo "Backing up current venv..."
    BACKUP_NAME="venv_backup_$(date +%Y%m%d_%H%M%S)"
    mv venv "$BACKUP_NAME"
    echo "✓ Backed up to $BACKUP_NAME"
    echo ""
fi

# Create fresh virtual environment
echo "Creating fresh virtual environment..."
python3.10 -m venv venv
echo "✓ Virtual environment created"
echo ""

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo "✓ pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Check for melspectrogram.onnx (required by openwakeword)
MELSPEC_PATH="venv/lib/python3.10/site-packages/openwakeword/resources/models/melspectrogram.onnx"
if [ ! -f "$MELSPEC_PATH" ]; then
    echo "⚠ melspectrogram.onnx not found, looking for backup..."
    BACKUP_MELSPEC=$(find venv_backup*/lib/python3.*/site-packages/openwakeword/resources/models/melspectrogram.onnx 2>/dev/null | head -1)
    if [ -n "$BACKUP_MELSPEC" ]; then
        echo "Copying melspectrogram.onnx from backup..."
        mkdir -p "$(dirname "$MELSPEC_PATH")"
        cp "$BACKUP_MELSPEC" "$MELSPEC_PATH"
        echo "✓ melspectrogram.onnx restored from backup"
    else
        echo "⚠ WARNING: melspectrogram.onnx not found. Openwakeword may download it on first use."
    fi
else
    echo "✓ melspectrogram.onnx found"
fi
echo ""

# Test critical imports
echo "Testing critical imports..."
python3 -c "
import sys
import signal

def timeout_handler(signum, frame):
    print('ERROR: Import test timed out!')
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(10)

print('  - Testing OpenAI...')
from openai import OpenAI
print('  ✓ OpenAI imports successfully')

print('  - Testing numpy...')
import numpy as np
print('  ✓ NumPy imports successfully')

print('  - Testing soundfile...')
import soundfile as sf
print('  ✓ soundfile imports successfully')

print('  - Testing pyaudio...')
import pyaudio
print('  ✓ pyaudio imports successfully')

signal.alarm(0)
print('')
print('All critical imports successful!')
"

echo ""
echo "=================================================="
echo "Virtual environment rebuilt successfully!"
echo "=================================================="
echo ""
echo "Run './run.sh' to start the application"
