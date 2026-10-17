[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($ProjectRoot) -ne "D:\") {
    throw "TraceRepair demo must run from D:. Current path: $ProjectRoot"
}

Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "D: virtual environment is missing. Run scripts\setup.ps1 first."
}

$env:TEMP = Join-Path $ProjectRoot "tmp"
$env:TMP = $env:TEMP
$Database = Join-Path $ProjectRoot "data\model-agent.sqlite3"
if (Test-Path -LiteralPath $Database) {
    & $Python scripts\export_web_demo.py
    if ($LASTEXITCODE -ne 0) { throw "Demo data export failed." }
}

$Index = Join-Path $ProjectRoot "demo\dist\index.html"
if (-not (Test-Path -LiteralPath $Index)) {
    throw "Demo artifact is missing. Run scripts\verify.ps1 first."
}

$Url = "http://127.0.0.1:$Port/"
Write-Host "TraceRepair demo: $Url" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the local-only server."
if (-not $NoBrowser) {
    Start-Process $Url
}
& $Python -m http.server $Port --bind 127.0.0.1 --directory (Join-Path $ProjectRoot "demo\dist")
