$Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "D:\AI-Content-Hub\admin-server\_launcher.vbs"
$Trigger = New-ScheduledTaskTrigger -AtLogon
Register-ScheduledTask -TaskName "AI-Content-Hub-Admin" -Action $Action -Trigger $Trigger -RunLevel Highest -Force
