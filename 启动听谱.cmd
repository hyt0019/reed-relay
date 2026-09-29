@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Please run setup.ps1 first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m reed_relay.app --converter
