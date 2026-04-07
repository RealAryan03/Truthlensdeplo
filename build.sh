#!/bin/bash
set -e
echo "Installing Python dependencies..."
pip install -r requirements.txt
echo "Downloading spaCy model..."
python -m spacy download en_core_web_sm || echo "Warning: spaCy model download may fail; will fallback to blank tokenizer"
echo "Build complete!"
