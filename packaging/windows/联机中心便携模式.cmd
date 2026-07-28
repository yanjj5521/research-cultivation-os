@echo off
setlocal
cd /d "%~dp0"
echo 本次使用当前文件夹中的 hub_data 保存联机中心账号、同步状态和备份。
"%~dp0ResearchHub.exe" --portable
endlocal
