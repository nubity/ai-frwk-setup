#!/bin/bash
# AI Framework - Workspace Setup (macOS Launcher)
#
# Double-click this file to initialize a new project workspace.
# Downloads and executes the bootstrap script with interactive prompts.
#
# Prerequisite: Python 3.11+ in PATH.
#
# If macOS shows "cannot be opened because it is from an unidentified developer":
#   Right-click → Open → Open (bypass Gatekeeper once).
#

set -euo pipefail

echo ""
echo "  AI Framework - Workspace Setup"
echo "  ================================"
echo ""

# Verify python3 is available.
if ! command -v python3 &>/dev/null; then
    echo "  [!!] python3 not found."
    echo "  [!!] Install Python 3.11+ (https://www.python.org/downloads/)."
    echo ""
    read -rp "  Press Enter to close..."
    exit 1
fi

# Download bootstrap.py using Python's stdlib (no curl dependency).
echo "  Downloading bootstrap script..."

BOOTSTRAP_URL="https://raw.githubusercontent.com/nubity/ai-frwk-setup/main/bootstrap.py"
TEMP_SCRIPT="$(mktemp /tmp/nubity-bootstrap.XXXXXX.py)"

cleanup() {
    rm -f "$TEMP_SCRIPT"
}
trap cleanup EXIT

if ! python3 -c "import urllib.request; urllib.request.urlretrieve('${BOOTSTRAP_URL}', '${TEMP_SCRIPT}')" 2>/dev/null; then
    echo "  [!!] Failed to download the bootstrap script."
    echo "  [!!] Check your internet connection and try again."
    echo ""
    read -rp "  Press Enter to close..."
    exit 1
fi

echo "  [OK] Downloaded."
echo ""

# Run the bootstrap in interactive mode (no arguments = prompts).
python3 "$TEMP_SCRIPT" "$@"

echo ""
read -rp "  Press Enter to close..."
