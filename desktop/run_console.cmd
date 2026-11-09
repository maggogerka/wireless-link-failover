@echo off
setlocal
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%APP_PYTHON%" (
    echo Virtual environment was not found.
    echo Open a terminal in the desktop folder and run:
    echo   python -m venv .venv
    echo   .venv\Scripts\python -m pip install -e .
    pause
    exit /b 1
)

"%APP_PYTHON%" -m wlf_console
if errorlevel 1 pause

