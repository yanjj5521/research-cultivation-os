@echo off
setlocal
cd /d "%~dp0"
set "TARGET=%CD%\ResearchOS.exe"
set "WORKDIR=%CD%"
set "SHORTCUT=%USERPROFILE%\Desktop\问道科研.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');$s.TargetPath='%TARGET%';$s.WorkingDirectory='%WORKDIR%';$s.IconLocation='%TARGET%,0';$s.Save()"
if errorlevel 1 (
  echo 无法创建桌面快捷方式。
) else (
  echo 已创建桌面快捷方式；不需要管理员权限。
)
pause
endlocal
