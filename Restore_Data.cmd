@echo off
cd /d "%~dp0"
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD set "PY_CMD=python"
%PY_CMD% restore_data.py
pause
