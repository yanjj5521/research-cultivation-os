@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo 请在资源管理器中打开旧版问道科研文件夹，复制地址栏中的完整路径。
echo 该文件夹里面应能看到 instance 和 storage。
echo.
set /p "OLD_DIR=请粘贴旧版文件夹路径："
if not defined OLD_DIR goto :cancelled
"%~dp0ResearchOS.exe" --migrate-from "%OLD_DIR%"
if errorlevel 1 goto :failed
echo.
echo 迁移完成。现在可以双击 ResearchOS.exe 启动。
pause
exit /b 0

:cancelled
echo 未输入路径，已取消。
pause
exit /b 1

:failed
echo 迁移失败。请确认选择的是包含 instance 和 storage 的旧版根目录。
pause
exit /b 1
