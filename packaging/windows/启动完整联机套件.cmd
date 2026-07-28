@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0ResearchHub.exe"
timeout /t 2 /nobreak >nul
start "" "%~dp0ResearchOS.exe"
endlocal
