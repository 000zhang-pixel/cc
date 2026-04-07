@echo off
:: setup_autostart_win.bat — 在 Windows 上用任务计划程序注册开机自启
:: 以普通用户权限运行即可（登录时触发）

set MIDDLEWARE_DIR=%~dp0
set PROJECT_DIR=%MIDDLEWARE_DIR%..
set LOG_DIR=%PROJECT_DIR%logs
set TASK_NAME=AI-Content-Hub-Middleware

:: 找 Python（优先虚拟环境，其次系统）
if exist "%MIDDLEWARE_DIR%.venv\Scripts\python.exe" (
    set PYTHON=%MIDDLEWARE_DIR%.venv\Scripts\python.exe
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set PYTHON=%%i
        goto :found_python
    )
    echo ERROR: python not found in PATH
    exit /b 1
)
:found_python

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: 创建 VBScript 无窗口启动器
set LAUNCHER=%MIDDLEWARE_DIR%_launcher.vbs
(
echo Set oShell = CreateObject^("WScript.Shell"^)
echo oShell.CurrentDirectory = "%MIDDLEWARE_DIR%"
echo oShell.Run """%PYTHON%"" ""%MIDDLEWARE_DIR%main.py"" >> ""%LOG_DIR%middleware.log"" 2^>^&1", 0, False
) > "%LAUNCHER%"

:: 注册任务计划程序（用户登录时触发，不弹窗）
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
schtasks /create /tn "%TASK_NAME%" ^
  /tr "wscript.exe \"%LAUNCHER%\"" ^
  /sc onlogon ^
  /delay 0000:30 ^
  /rl limited ^
  /f

if %errorlevel% == 0 (
    echo 已注册任务: %TASK_NAME%
    echo 日志: %LOG_DIR%middleware.log
    echo.
    echo 常用命令:
    echo   schtasks /run /tn "%TASK_NAME%"      启动
    echo   schtasks /end /tn "%TASK_NAME%"      停止
    echo   schtasks /delete /tn "%TASK_NAME%" /f  移除
) else (
    echo 注册失败，请检查权限
)
