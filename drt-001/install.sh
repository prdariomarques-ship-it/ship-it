#!/bin/bash

# DRT-001 Installation Script
# One-command setup for fresh machines

set -e

echo "====================================="
echo "DRT-001 Runtime Installation"
echo "====================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required"
    exit 1
fi

echo "✓ Python version: $(python3 --version)"
echo ""

# Install dependencies
echo "Installing dependencies..."
python3 -m pip install -q -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Validate storage
echo "Validating storage..."
python3 << 'PYTHON'
import sys
sys.path.insert(0, 'src')
from persistence import FilePersistence
p = FilePersistence()
if p.validate_storage():
    print('✓ Storage validation passed')
else:
    print('ERROR: Storage validation failed')
    exit(1)
PYTHON
echo ""

# Verify imports
echo "Verifying imports..."
python3 << 'PYTHON'
import sys
sys.path.insert(0, 'src')
from persistence import FilePersistence
from execution_tracker import ExecutionTracker
from workflow_engine import WorkflowEngine
print('✓ All imports successful')
PYTHON
echo ""

echo "====================================="
echo "Installation complete!"
echo ""
echo "To start the Runtime:"
echo "  python3 -m src.runtime_api"
echo ""
echo "Runtime will listen on http://localhost:8000"
echo "====================================="
