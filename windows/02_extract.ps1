
param(
    [Parameter(Mandatory = $true)]
    [string]$InputVideo,
    [string]$OutputFramesDir
)

$videoPath = Convert-Path $InputVideo
if (-not $OutputFramesDir) {
    $parent = Split-Path -Parent $videoPath
    $OutputFramesDir = Join-Path $parent "tmp_frames"
}

New-Item -ItemType Directory -Force -Path $OutputFramesDir | Out-Null

# Clean dir
Remove-Item -Path "$OutputFramesDir\*" -Force -ErrorAction SilentlyContinue

Write-Host "Extracting frames from $videoPath to $OutputFramesDir" -ForegroundColor Cyan
& ffmpeg -i $videoPath -f image2 "$OutputFramesDir\%06d.png" 2>&1 | Out-Null
Write-Host "Extraction Complete" -ForegroundColor Green
