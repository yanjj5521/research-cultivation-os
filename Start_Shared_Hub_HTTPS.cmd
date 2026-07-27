@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "HUB_HTTPS_ONLY=1"
set "HUB_TRUST_PROXY=1"
set /p HUB_ALLOWED_HOSTS=Enter the public hostname only (example hub.example.com):
if "%HUB_ALLOWED_HOSTS%"=="" (
  echo A public hostname is required.
  pause
  exit /b 1
)
call Start_Shared_Hub.cmd
endlocal
