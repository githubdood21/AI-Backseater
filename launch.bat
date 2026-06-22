@echo off
title AI-Backseater
cd /d "%~dp0"

:: Check if setup is needed by looking for venv or key dependency dirs
if not exist "venv\Scripts\python.exe" (
    echo [First launch] Setting up environment...
    call setup.bat
    if %errorlevel% neq 0 (
        pause
        exit /b %errorlevel%
    )
)

:: Re-check if setup succeeded
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup.bat manually.
    pause
    exit /b 1
)

:: Activate venv and launch app
call venv\Scripts\activate.bat
python main.py
if %errorlevel% neq 0 (
    echo.
    echo Application exited with error code %errorlevel%.
    pause
)