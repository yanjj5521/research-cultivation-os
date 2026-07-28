@echo off
setlocal
cd /d "%~dp0"
echo 本次使用当前文件夹中的 user_data 保存全部个人数据。
"%~dp0ResearchOS.exe" --portable
endlocal
