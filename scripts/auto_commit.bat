@echo off
REM 每天定时自动提交脚本（由 Windows 任务计划触发）
REM 任务计划设置: 每天 23:00 运行此文件

"C:\Program Files\Git\usr\bin\bash.exe" "D:/AI-Content-Hub/scripts/auto_commit.sh" >> "D:/AI-Content-Hub/logs/auto_commit.log" 2>&1
