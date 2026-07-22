@echo off
REM VYON Backend Startup Script
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m uvicorn app:app --reload --port 8000 --host 0.0.0.0
pause
