@echo off
REM ============================================================
REM GitMind: Start Script
REM Launches backend (FastAPI), frontend (Next.js), and browser
REM ============================================================

REM ── 0. Check ports ──
REM Fail early instead of letting Next.js move to another port: the
REM browser, CORS_ORIGINS and the OAuth callback all expect 3000 and 8000.
echo [0/4] Checking that ports 8000 and 3000 are free...
call :check_port 8000 || goto :fail
call :check_port 3000 || goto :fail

REM ── 1. Backend Setup ──
echo [1/4] Setting up backend environment...
cd /d "%~dp0backend"

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo       [ERROR] uv is not installed. Install it with: pip install uv
    goto :fail
)

echo       Installing locked dependencies, this may take a moment...
uv sync
if %errorlevel% neq 0 (
    echo       [ERROR] uv sync failed. Check the error above.
    goto :fail
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
start "GitMind Backend" cmd /k "uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM ── 3. Frontend Setup & Start ──
echo [3/4] Starting Next.js frontend on port 3000...
cd /d "%~dp0frontend"

REM Always sync: fast when up to date, and keeps node_modules in line with
REM package-lock.json after switching branches or pulling upgrades
echo       Syncing frontend dependencies...
call npm install --no-audit --no-fund --silent
if %errorlevel% neq 0 (
    echo       [ERROR] npm install failed. Check the error above.
    goto :fail
)

REM Copy .env.local if it doesn't exist
if not exist .env.local (
    echo       Creating .env.local from template...
    copy .env.local.example .env.local >nul
)

REM An explicit port makes Next.js fail instead of silently switching to 3001
start "GitMind Frontend" cmd /k "npm run dev -- --port 3000"

REM ── 4. Open Browser ──
echo [4/4] Opening dashboard in browser...
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo.
echo  All services started!
echo  Backend:   http://localhost:8000
echo  Frontend:  http://localhost:3000
echo  API Docs:  http://localhost:8000/docs
echo  Close the "GitMind Backend" and "GitMind Frontend" windows to stop.
echo.
exit /b 0

:check_port
REM Returns 1 and prints the owning process when %1 is already in use
netstat -ano | findstr /R /C:":%1 .*LISTENING" >nul
if %errorlevel% neq 0 exit /b 0
echo       [ERROR] Port %1 is already in use, probably by a previous GitMind run:
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%1 .*LISTENING"') do (
    for /f "tokens=1" %%n in ('tasklist /FI "PID eq %%p" /NH') do echo               PID %%p, process %%n
)
echo       Close the old GitMind windows, or stop the process with: taskkill /PID ^<pid^> /T /F
exit /b 1

:fail
echo.
echo  Startup aborted.
pause
exit /b 1
