# Lazy Job Hunter daily run. The scheduled task "LazyJobHunter-Daily" calls this every morning.
# Profiles to run: one path per line in daily_profiles.txt (relative to this folder).
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
New-Item -ItemType Directory -Force "$here\logs", "$here\tmp" | Out-Null
$env:TMP = "$here\tmp"; $env:TEMP = "$here\tmp"; $env:PYTHONIOENCODING = 'utf-8'
$log = "$here\logs\daily_$(Get-Date -Format yyyyMMdd).log"
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = 'python' }
Get-Content "$here\daily_profiles.txt" | Where-Object { $_.Trim() -and -not $_.StartsWith('#') } | ForEach-Object {
    "=== $(Get-Date -Format s) $_" | Out-File $log -Append -Encoding utf8
    & $py "$here\jobhunter.py" --profile $_.Trim() --label daily *>&1 | Out-File $log -Append -Encoding utf8
}
