@echo off
REM ============================================================
REM GitMind — Start Script
REM Launches backend (FastAPI), frontend (Next.js), and browser
REM ============================================================

REM ── 1. Backend Setup ──
echo [1/4] Setting up backend virtual environment...
cd /d "%~dp0backend"

if not exist venv (
    echo       Creating virtual environment...
    python -m venv venv
)

echo       Activating venv and installing dependencies...
call venv\Scripts\activate.bat
echo       Installing dependencies (this may take a moment)...
pip install -e ".[dev]"
if %errorlevel% neq 0 (
    echo       [ERROR] Failed to install dependencies. Check the error above.
    echo       You may need to run: pip install -e ".[dev]" manually
    pause
    exit /b 1
)

REM Copy .env if it doesn't exist
if not exist .env (
    echo       Creating .env from template...
    copy .env.example .env >nul
    echo       [!] Please edit backend\.env with your API keys before using the app.
)

REM ── 2. Start Backend ──
echo [2/4] Starting FastAPI backend on port 8000...
cd /d "%~dp0backend"
start "GitMind Backend" cmd /k "call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM ── 3. Frontend Setup & Start ──
echo [3/4] Starting Next.js frontend on port 3000...
cd /d "%~dp0frontend"

if not exist node_modules (
    echo       Installing frontend dependencies...
    call npm install --silent
)

REM Copy .env.local if it doesn't exist
if not exist .env.local (
    echo       Creating .env.local from template...
    copy .env.local.example .env.local >nul
)

start "GitMind Frontend" cmd /k "npm run dev"

REM ── 4. Open Browser ──
echo [4/4] Opening dashboard in browser...
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo.
echo  All services started!
echo  Backend:   http://localhost:8000      
echo  Frontend:  http://localhost:3000      
echo  API Docs:  http://localhost:8000/docs                                        
echo  Close the terminal windows to stop.
echo.
