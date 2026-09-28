#!/bin/bash
# ============================================================
# GitMind: Start Script for Mac/Linux
# Launches backend (FastAPI), frontend (Next.js), and browser
# ============================================================

# Ensure all background processes are terminated when the script exits
trap "kill 0" EXIT

# Get the absolute path to the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# ── 0. Check ports ──
# Fail early instead of letting Next.js move to another port: the browser,
# CORS_ORIGINS and the OAuth callback all expect 3000 and 8000.
port_in_use() {
    if command -v lsof > /dev/null; then
        lsof -iTCP:"$1" -sTCP:LISTEN -t > /dev/null 2>&1
    else
        (echo > "/dev/tcp/127.0.0.1/$1") > /dev/null 2>&1
    fi
}

echo "[0/4] Checking that ports 8000 and 3000 are free..."
for port in 8000 3000; do
    if port_in_use "$port"; then
        echo "      [ERROR] Port $port is already in use, probably by a previous GitMind run."
        if command -v lsof > /dev/null; then
            lsof -iTCP:"$port" -sTCP:LISTEN -P -n | sed 's/^/              /'
        fi
        echo "      Stop that process (kill <pid>) and run this script again."
        exit 1
    fi
done

# ── 1. Backend Setup ──
echo "[1/4] Setting up backend environment..."
cd "$DIR/backend"

if ! command -v uv > /dev/null; then
    echo "      [ERROR] uv is not installed. Install it with: pip install uv"
    exit 1
fi

echo "      Installing locked dependencies (this may take a moment)..."
uv sync || { echo "      [ERROR] uv sync failed. Check the error above."; exit 1; }

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "      Creating .env from template..."
    cp .env.example .env 2>/dev/null || true
    echo "      [!] Please edit backend/.env with your API keys before using the app."
fi

# ── 2. Start Backend ──
echo "[2/4] Starting FastAPI backend on port 8000 in background..."
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &

# Wait a moment for backend to initialize
sleep 3

# ── 3. Frontend Setup & Start ──
echo "[3/4] Setting up Next.js frontend..."
cd "$DIR/frontend"

# Always sync: fast when up to date, and keeps node_modules in line with
# package-lock.json after switching branches or pulling upgrades
echo "      Syncing frontend dependencies..."
npm install --no-audit --no-fund --silent || { echo "      [ERROR] npm install failed. Check the error above."; exit 1; }

# Copy .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
    echo "      Creating .env.local from template..."
    cp .env.local.example .env.local 2>/dev/null || true
fi

echo "[3/4] Starting Next.js frontend on port 3000 in background..."
# An explicit port makes Next.js fail instead of silently switching to 3001
npm run dev -- --port 3000 &

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
