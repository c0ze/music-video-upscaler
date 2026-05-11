[CmdletBinding()]
param(
  [string]$WebHost = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Venv = Join-Path $ScriptDir ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
  Write-Host "Creating venv at $Venv..."
  python -m venv $Venv
  & $Py -m pip install --upgrade pip | Out-Null
  & $Py -m pip install -r (Join-Path $ScriptDir "requirements.txt")
}

Push-Location $RepoRoot
try {
  Write-Host "Starting music-video-upscaler web UI on http://${WebHost}:$Port"
  & $Py -m uvicorn web.server:app --host $WebHost --port $Port
} finally {
  Pop-Location
}
