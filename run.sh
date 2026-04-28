#!/bin/bash

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r backend/requirements.txt

# Start the application
echo "Starting AmneziaWG Gen..."
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
