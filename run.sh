#!/bin/bash
# Convenience script to run J.F. Sebastian AI system

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and configure your API keys."
    exit 1
fi

# Run the application
python -m teddy_ruxpin.main
