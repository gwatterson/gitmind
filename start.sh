#!/bin/bash
# ============================================================
# GitMind — Start Script for Mac/Linux
# Launches backend (FastAPI), frontend (Next.js), and browser
# ============================================================

# Ensure all background processes are terminated when the script exits
trap "kill 0" EXIT

# Get the absolute path to the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# ── 1. Backend Setup ──
echo "[1/4] Setting up backend virtual environment..."
cd "$DIR/backend"

if [ ! -d "venv" ]; then
    echo "      Creating virtual environment..."
    python3 -m venv venv || python -m venv venv
fi

echo "      Activating venv and installing dependencies..."
source venv/bin/activate

echo "      Installing dependencies (this may take a moment)..."
pip install -e ".[dev]"

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "      Creating .env from template..."
    cp .env.example .env 2>/dev/null || true
    echo "      [!] Please edit backend/.env with your API keys before using the app."
fi

# ── 2. Start Backend ──
echo "[2/4] Starting FastAPI backend on port 8000 in background..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &

# Wait a moment for backend to initialize
sleep 3

# ── 3. Frontend Setup & Start ──
echo "[3/4] Setting up Next.js frontend..."
cd "$DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo "      Installing frontend dependencies..."
    npm install --silent
fi

# Copy .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
    echo "      Creating .env.local from template..."
    cp .env.local.example .env.local 2>/dev/null || true
fi

echo "[3/4] Starting Next.js frontend on port 3000 in background..."
npm run dev &

# ── 4. Open Browser ──
echo "[4/4] Opening dashboard in browser..."
sleep 5

if command -v xdg-open > /dev/null; then
  # Linux
  xdg-open http://localhost:3000 > /dev/null 2>&1
elif command -v open > /dev/null; then
  # Mac
  open http://localhost:3000 > /dev/null 2>&1
else
  echo "      [!] Could not detect browser command. Please open http://localhost:3000 manually."
fi

echo ""
echo "============================================================"
echo " All services started successfully!"
echo " Backend:   http://localhost:8000"
echo " Frontend:  http://localhost:3000"
echo " API Docs:  http://localhost:8000/docs"
echo ""
echo " IMPORTANT: Press Ctrl+C in this terminal to stop all services."
echo "============================================================"
echo ""

# Keep the script running to hold the background processes
wait
