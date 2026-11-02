@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv\Scripts\python.exe
    echo Run: uv venv .venv ^& uv pip install -r requirements.txt
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\run_tv.py" %*
exit /b %ERRORLEVEL%
