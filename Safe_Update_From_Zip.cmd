@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" safe_update.py
) else (
  py -3 safe_update.py
)
pause
