# Native Windows dependency bootstrap (PowerShell 5+).
# Installs FFmpeg via winget when available and yt-dlp via pip.
# Real-ESRGAN Windows binary is not redistributed here; place:
#   windows\realesrgan-ncnn-vulkan.exe
# alongside the scripts (see README).
#
# Optional flags:
#   -WithWeb   Also create web\.venv and install web UI dependencies.

[CmdletBinding()]
param(
    [switch]$WithWeb
)

$ErrorActionPreference = "Continue"

function Test-CommandExists([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Format-OkMissing([bool]$Ok) {
    if ($Ok) { return "OK" }
    return "MISSING"
}

Write-Host "Installing / verifying dependencies for music-video-upscaler (Windows)..."

if (-not (Test-CommandExists ffmpeg) -or -not (Test-CommandExists ffprobe)) {
    if (Test-CommandExists winget) {
        Write-Host "Installing FFmpeg via winget..."
        winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    }
    elseif (Test-CommandExists choco) {
        Write-Host "Installing FFmpeg via Chocolatey..."
        choco install ffmpeg -y
    }
    else {
        Write-Host "Install FFmpeg manually and ensure ffmpeg/ffprobe are on PATH." -ForegroundColor Yellow
    }
}

if (-not (Test-CommandExists yt-dlp)) {
    if (Test-CommandExists python) {
        Write-Host "Installing yt-dlp via pip..."
        python -m pip install --user --upgrade yt-dlp
    }
    elseif (Test-CommandExists python3) {
        python3 -m pip install --user --upgrade yt-dlp
    }
    else {
        Write-Host "Install Python 3 and run: python -m pip install --user yt-dlp" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Dependency check:"
Write-Host ("  ffmpeg:  " + (Format-OkMissing (Test-CommandExists ffmpeg)))
Write-Host ("  ffprobe: " + (Format-OkMissing (Test-CommandExists ffprobe)))
Write-Host ("  yt-dlp:  " + (Format-OkMissing (Test-CommandExists yt-dlp)))

$re = Join-Path $PSScriptRoot "realesrgan-ncnn-vulkan.exe"
if (Test-Path $re) {
    Write-Host "  realesrgan-ncnn-vulkan: OK ($re)"
}
else {
    Write-Host "  realesrgan-ncnn-vulkan: NOT FOUND under windows\ — add the portable build." -ForegroundColor Yellow
}

if ($WithWeb) {
    Write-Host ""
    Write-Host "Installing web UI dependencies..."
    $RepoRoot = Split-Path -Parent $PSScriptRoot
    $WebDir = Join-Path $RepoRoot "web"
    $Venv = Join-Path $WebDir ".venv"
    $PythonCmd = $null
    if (Test-CommandExists python) { $PythonCmd = "python" }
    elseif (Test-CommandExists python3) { $PythonCmd = "python3" }
    if ($null -eq $PythonCmd) {
        Write-Host "WARNING: python not found; skipping web UI install." -ForegroundColor Yellow
    } else {
        & $PythonCmd -m venv $Venv
        & (Join-Path $Venv "Scripts\pip.exe") install --upgrade pip | Out-Null
        & (Join-Path $Venv "Scripts\pip.exe") install -r (Join-Path $WebDir "requirements.txt")
        Write-Host "Web UI installed. Run with: web\run_server.ps1"
    }
}

Write-Host ""
Write-Host "Done."
