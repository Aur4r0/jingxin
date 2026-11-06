@echo off
setlocal
set PYTHONUTF8=1
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 scripts\windows_bootstrap.py
  if errorlevel 1 goto failed
  goto done
)
where python >nul 2>&1
if errorlevel 1 goto missing
python scripts\windows_bootstrap.py
if errorlevel 1 goto failed
:done
echo.
echo 配置完成。双击 start-windows.cmd 启动。
popd
pause
exit /b 0
:missing
echo 请先安装 Python 3.12 64 位，并安装 Python Launcher 或勾选 Add Python to PATH。
echo 官方下载：https://www.python.org/downloads/windows/
:failed
echo 配置未完成。请查看上方错误，解决后重新运行，不要删除 .env 或数据库。
popd
pause
exit /b 1
