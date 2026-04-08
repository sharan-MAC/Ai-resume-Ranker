#!/bin/bash
echo "================================================"
echo "   Recruit.AI - Starting Server"
echo "================================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Please install Python 3.9+"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Create required directories
mkdir -p resumes_raw templates

# Start the server
echo ""
echo "Starting server on http://0.0.0.0:3000"
echo "Default login: admin / admin123"
echo "================================================"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
