# Same task as install_schedule.ps1, with a chosen time.
#   Demo now:      .\install_schedule_at.ps1 -InMinutes 5
#   Back to daily: .\install_schedule_at.ps1 -At 7:50am
# Undo any time: Unregister-ScheduledTask -TaskName LazyJobHunter-Daily -Confirm:$false
param([string]$At = '7:50am', [int]$InMinutes = 0)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($InMinutes -gt 0) { $t0 = (Get-Date).AddMinutes($InMinutes); $when = $t0.Date.AddHours($t0.Hour).AddMinutes($t0.Minute) } else { $when = [datetime]$At }
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$here\run_daily.ps1`"" -WorkingDirectory $here
$t = New-ScheduledTaskTrigger -Daily -At $when
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'LazyJobHunter-Daily' -Action $a -Trigger $t -Settings $s -Force `
    -Description 'Lazy Job Hunter: top 3 new jobs to Telegram before 8 AM' | Out-Null
$i = Get-ScheduledTask -TaskName 'LazyJobHunter-Daily' | Get-ScheduledTaskInfo
"Scheduled daily at $($when.ToString('h:mm tt')). Next run: $($i.NextRunTime)"
