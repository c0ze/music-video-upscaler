
param(
    [Parameter(Mandatory = $true)]
    [string]$FramesDir,
    [Parameter(Mandatory = $true)]
    [string]$AudioPath,
    [Parameter(Mandatory = $false)]
    [string]$OriginalVideo,
    [double]$Fps = 30,
    [string]$OutputVideo
)

if (-not $OutputVideo) {
    Write-Host "Error: OutputVideo path required"
    exit 1
}

$parent = Split-Path -Parent $OutputVideo
if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }

if ($OriginalVideo -and (Test-Path $OriginalVideo)) {
    Write-Host "Extracting FPS from $OriginalVideo..."
    $fps = (& ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 $OriginalVideo).Trim()
}

Write-Host "Muxing frames + audio at FPS: $fps" -ForegroundColor Cyan

# Mux
& ffmpeg -framerate $fps -i "$FramesDir\%06d.png" -i $AudioPath -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -map 0:v:0 -map 1:a:0 $OutputVideo

Write-Host "Done: $OutputVideo" -ForegroundColor Green
