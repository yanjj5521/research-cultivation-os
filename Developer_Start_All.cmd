@echo off
setlocal
cd /d "%~dp0"
start "Research Hub Dev" cmd /k call "%~dp0Start_Shared_Hub.cmd"
timeout /t 2 /nobreak >nul
start "Research OS Dev" cmd /k call "%~dp0Start_Research_OS.cmd"
endlocal
