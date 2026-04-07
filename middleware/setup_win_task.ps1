# setup_win_task.ps1 — 注册 Windows 开机自启任务
# 用法: powershell -ExecutionPolicy Bypass -File setup_win_task.ps1

$PYTHON = "C:\Users\carson\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$MIDDLEWARE = "D:\AI-Content-Hub\middleware"
$LOG = "D:\AI-Content-Hub\logs\middleware.log"
$TASK = "AI-Content-Hub-Middleware"

# 确保日志目录存在
New-Item -ItemType Directory -Force -Path (Split-Path $LOG) | Out-Null

# 构造 PowerShell 启动命令
$psCmd = "Set-Location '$MIDDLEWARE'; & '$PYTHON' main.py *>> '$LOG'"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$psCmd`""

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT30S"   # 登录后延迟 30 秒再启动

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit 0 `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask `
    -TaskName $TASK `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "已注册任务: $TASK"
Write-Host "日志: $LOG"
Write-Host ""
Write-Host "立即启动中..."
Start-ScheduledTask -TaskName $TASK
Start-Sleep 5

if (Test-Path $LOG) {
    Write-Host "--- 最新日志 ---"
    Get-Content $LOG -Tail 20
} else {
    Write-Host "日志文件尚未创建，请检查 Python 路径是否正确"
}
