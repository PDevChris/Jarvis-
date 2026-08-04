#!/usr/bin/env bash
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN} --------------------------------------------------"
echo -e "  JARVIS CORE STARTING..."
echo -e " --------------------------------------------------${NC}"
echo ""

# Require Python 3
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo -e "${RED} [ERROR] Python 3 not found. Install Python 3.10+ and try again.${NC}"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Install dependencies quietly
echo " [1/2] Checking dependencies..."
"$PYTHON" -m pip install -q -r requirements.txt

# Kill any stale process on port 8000
if lsof -i :8000 -t &>/dev/null 2>&1; then
    echo "       Stopping stale server on port 8000..."
    lsof -i :8000 -t | xargs kill -9 2>/dev/null || true
    sleep 0.5
fi

echo " [2/2] Starting JARVIS backend on http://localhost:8000"
echo ""
echo -e "${GREEN} JARVIS is ready. Open Chrome and navigate to http://localhost:8000${NC}"
echo " Press Ctrl+C to stop."
echo ""

"$PYTHON" jarvis_proxy.py
