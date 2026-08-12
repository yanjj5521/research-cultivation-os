@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0一键上传到GitHub.ps1"
if errorlevel 1 (
  echo.
  echo Upload failed. Please read the error above.
  pause
)
