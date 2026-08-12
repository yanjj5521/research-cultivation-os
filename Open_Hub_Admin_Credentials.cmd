@echo off
cd /d "%~dp0"
if exist "instance\HUB_ADMIN_CREDENTIALS.txt" (
  start "" notepad "instance\HUB_ADMIN_CREDENTIALS.txt"
) else (
  echo Credentials file not found. Start the Shared Hub once first.
  pause
)
