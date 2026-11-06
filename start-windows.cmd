@echo off
setlocal
set PYTHONUTF8=1
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo 请先双击 setup-windows.cmd 完成配置。
  goto failed
)
".venv\Scripts\python.exe" scripts\doctor.py
if errorlevel 1 goto failed
echo.
echo 服务即将启动，请在浏览器打开 http://127.0.0.1:8000
echo 如已启用策略，启动后会恢复定时执行。关闭服务请按 Ctrl+C。
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto failed
popd
exit /b 0
:failed
echo 启动失败，请查看上方错误。
popd
pause
exit /b 1
