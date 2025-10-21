#!/usr/bin/env bash
# Upload package to PyPI using credentials from .env file

set -e

# Load environment variables from .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found"
    echo "Copy .env.example to .env and add your PyPI token"
    exit 1
fi

# Check if token is set
if [ -z "$PYPI_TOKEN" ] || [ "$PYPI_TOKEN" = "pypi-your-token-here" ]; then
    echo "Error: PYPI_TOKEN not set in .env file"
    echo "Get your token from: https://pypi.org/manage/account/token/"
    exit 1
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Clean old builds
echo "Cleaning old build artifacts..."
rm -rf dist/ build/

# Build the package
echo "Building package..."
python -m build

# Check the package
echo "Checking package..."
twine check dist/*

# Upload to PyPI
echo "Uploading to PyPI..."
TWINE_USERNAME="__token__" TWINE_PASSWORD="$PYPI_TOKEN" twine upload dist/*

echo "✅ Successfully uploaded to PyPI!"
