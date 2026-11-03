# Run this once to get your jobs every morning at 7:50 AM (your laptop must be on or asleep, not shut down).
# Undo any time: Unregister-ScheduledTask -TaskName LazyJobHunter-Daily -Confirm:$false
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$here\run_daily.ps1`"" -WorkingDirectory $here
$t = New-ScheduledTaskTrigger -Daily -At 7:50am
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'LazyJobHunter-Daily' -Action $a -Trigger $t -Settings $s -Force `
    -Description 'Lazy Job Hunter: top 3 new jobs to Telegram before 8 AM' | Out-Null
$i = Get-ScheduledTask -TaskName 'LazyJobHunter-Daily' | Get-ScheduledTaskInfo
"Scheduled. Next run: $($i.NextRunTime)"
