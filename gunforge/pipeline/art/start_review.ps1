# Restore the read-only review services after their processes exit or Windows restarts.
$ErrorActionPreference = 'Stop'
$artRoot = $PSScriptRoot
$reviewPython = Join-Path $artRoot '.venv/Scripts/python.exe'
$reviewServer = Join-Path $artRoot 'serve_t02_gallery.py'
if (-not (Test-Path -LiteralPath $reviewPython)) { throw "Missing Python environment: $reviewPython" }
$reviewLogs = Join-Path $artRoot '.review-logs'
New-Item -ItemType Directory -Path $reviewLogs -Force | Out-Null
foreach ($reviewSite in @(@{Port=8765;Task='T02'},@{Port=8766;Task='T03'},@{Port=8767;Task='T07'})) {
    $reviewListener = Get-NetTCPConnection -LocalPort $reviewSite.Port -State Listen -ErrorAction SilentlyContinue
    if (-not $reviewListener) {
        $reviewArguments = @('"' + $reviewServer + '"', '--port', [string]$reviewSite.Port, '--task', $reviewSite.Task)
        Start-Process -FilePath $reviewPython -ArgumentList $reviewArguments -WorkingDirectory $artRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reviewLogs ($reviewSite.Task+'.out.log')) -RedirectStandardError (Join-Path $reviewLogs ($reviewSite.Task+'.err.log')) | Out-Null
    }
}
Write-Output 'Current A2k review: http://127.0.0.1:8767/gallery/'
Write-Output 'Earlier T02 references: http://127.0.0.1:8765/gallery/'
