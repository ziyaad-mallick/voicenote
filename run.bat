@echo off
cd /d "%~dp0"
title VoiceNote

set PYTHON=C:\Users\testi\AppData\Local\Programs\Python\Python311\python.exe
set VENV=%~dp0.venv\Scripts\python.exe

:: Auto-create venv if missing
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Setting up VoiceNote for the first time...
    "%PYTHON%" -m venv .venv
    echo Installing dependencies...
    "%~dp0.venv\Scripts\python.exe" -m pip install faster-whisper sounddevice rich textual python-docx pyyaml winotify numpy scipy requests python-dateutil groq --quiet
    echo Done!
)

"%VENV%" main.py
