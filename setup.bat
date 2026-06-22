@echo off
title AI-Backseater Setup
echo ========================================
echo   AI-Backseater - First Time Setup
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10 or later from https://python.org
    pause
    exit /b 1
)

:: Check Python version
for /f "tokens=2" %%I in ('python --version 2^>^&1') do set PY_VER=%%I
echo [OK] Python %PY_VER% detected

:: Create venv if not exists
if not exist "venv\Scripts\python.exe" (
    echo [..] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

:: Activate venv
call venv\Scripts\activate.bat

:: Upgrade pip
echo [..] Upgrading pip...
python -m pip install --upgrade pip -q
echo [OK] Pip updated

:: Install dependencies
echo [..] Installing Python dependencies...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: Check for Kokoro repo
if not exist "kokoro\kokoro.py" (
    echo [..] Kokoro development checkout not found.
    echo      The published kokoro package was installed above from pip.
    echo      If you want to use a local development checkout, run:
    echo        git clone https://github.com/hexgrad/kokoro.git
) else (
    echo [OK] Kokoro local checkout found
)

echo.
echo ========================================
echo   Setup complete! You can now run:
echo       python main.py
echo   or double-click launch.bat
echo ========================================
pause