@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Project Python environment missing. Follow the README Quick start first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "scripts\backend_control.py"
