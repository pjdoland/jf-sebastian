#!/bin/bash
# Debug version of run script with comprehensive logging
# Use this to diagnose startup issues

set -x  # Print each command before executing
set -e  # Exit on error

echo "========================================="
echo "J.F. Sebastian - Debug Startup"
echo "========================================="
echo "Timestamp: $(date)"
echo "Working directory: $(pwd)"
echo ""

# Check Python availability
echo "--- Checking Python ---"
which python3 || echo "python3 not found"
python3 --version || echo "Failed to get python3 version"
echo ""

# Check virtual environment
echo "--- Checking Virtual Environment ---"
if [ -d "venv" ]; then
    echo "venv directory exists"
    ls -la venv/bin/ | head -10
    echo "Activating venv..."
    source venv/bin/activate
    echo "Active Python: $(which python3)"
    echo "Python version: $(python3 --version)"
else
    echo "ERROR: venv directory not found!"
    exit 1
fi
echo ""

# Check .env file
echo "--- Checking .env File ---"
if [ -f ".env" ]; then
    echo ".env file exists"
    echo "Keys in .env:"
    grep -E "^[A-Z_]+" .env | cut -d= -f1 | sort
else
    echo "ERROR: .env file not found!"
    echo "Please copy .env.example to .env and configure your API keys."
    exit 1
fi
echo ""

# Test basic imports
echo "--- Testing Python Imports ---"
echo "Testing: import sys"
python3 -c "import sys; print('sys: OK')" || echo "FAILED: sys"

echo "Testing: import numpy"
python3 -c "import numpy; print('numpy: OK')" || echo "FAILED: numpy"

echo "Testing: import soundfile"
python3 -c "import soundfile; print('soundfile: OK')" || echo "FAILED: soundfile"

echo "Testing: import jf_sebastian"
python3 -c "import jf_sebastian; print('jf_sebastian: OK')" || echo "FAILED: jf_sebastian"

echo "Testing: from jf_sebastian.config import settings"
python3 -c "from jf_sebastian.config import settings; print('settings: OK')" || echo "FAILED: settings"
echo ""

# Run with verbose logging
echo "========================================="
echo "Starting Application (verbose mode)"
echo "========================================="
echo ""

# Set Python to unbuffered mode for immediate output
export PYTHONUNBUFFERED=1

# Run the application
python3 -m jf_sebastian.main
