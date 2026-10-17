[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($ProjectRoot) -ne "D:\") {
    throw "TraceRepair must be installed on D:. Current path: $ProjectRoot"
}

Set-Location -LiteralPath $ProjectRoot
$env:TEMP = Join-Path $ProjectRoot "tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $ProjectRoot ".cache\pip"
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot ".cache\pycache"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR, $env:PYTHONPYCACHEPREFIX | Out-Null

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $BasePython = (Get-Command python -ErrorAction Stop).Source
    & $BasePython -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install -e "${ProjectRoot}[dev]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
Write-Host "TraceRepair setup completed on D:." -ForegroundColor Green
Write-Host "Next: powershell -ExecutionPolicy Bypass -File scripts\verify.ps1"
