
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetFolder,
    [string]$YouTubeUrl,
    [int]$Scale = 4
)

$WinDir = $PSScriptRoot
$TargetFolder = Convert-Path $TargetFolder

Write-Host "Running Upscale Pipeline on: $TargetFolder" -ForegroundColor Magenta

# 0. Sanitize
& "$WinDir\00_sanitize.ps1" -Directory $TargetFolder

# Find video and audio files (simple heuristic: largest webm/mkv/mp4 is video, largest flac/wav is audio)
$videoFile = Get-ChildItem $TargetFolder -Include *.webm, *.mkv, *.mp4 -Recurse | Sort-Object Length -Descending | Select-Object -First 1
$audioFile = Get-ChildItem $TargetFolder -Include *.flac, *.wav -Recurse | Where-Object { $_.Name -notmatch "_synced" -and $_.Name -notmatch "_youtube_audio" } | Sort-Object Length -Descending | Select-Object -First 1

if (-not $videoFile -or -not $audioFile) {
    Write-Host "Error: Could not identify video/audio pair in $TargetFolder" -ForegroundColor Red
    exit 1
}

Write-Host "Found Video: $($videoFile.Name)"
Write-Host "Found Audio: $($audioFile.Name)"

# 1. Sync
& "$WinDir\01_sync_audio.ps1" -InputVideo $videoFile.FullName -InputAudio $audioFile.FullName -YouTubeUrl $YouTubeUrl

# 2. Extract
$framesDir = Join-Path $TargetFolder "tmp_frames"
& "$WinDir\02_extract.ps1" -InputVideo $videoFile.FullName -OutputFramesDir $framesDir

# 3. Upscale
$upscaledDir = Join-Path $TargetFolder "tmp_upscaled_${Scale}x"
& "$WinDir\03_upscale.ps1" -InputFramesDir $framesDir -OutputUpscaledDir $upscaledDir -Scale $Scale

# 4. Mux
$videoBase = $videoFile.BaseName
$outputName = "${videoBase}_realesrgan_x4plus_${Scale}x_HQ.mkv"
$outputDir = Join-Path (Split-Path -Parent $TargetFolder) "METAL_VIDS_UPSCALED_FLAC"
$outputSubDir = Split-Path -Leaf $TargetFolder
$finalOutputDir = Join-Path $outputDir $outputSubDir
$finalOutputFile = Join-Path $finalOutputDir $outputName

if (-not (Test-Path $finalOutputDir)) { New-Item -ItemType Directory -Force -Path $finalOutputDir | Out-Null }

& "$WinDir\04_mux.ps1" -FramesDir $upscaledDir -AudioPath (Join-Path $TargetFolder "${videoBase}_synced.flac") -OriginalVideo $videoFile.FullName -OutputVideo $finalOutputFile

Write-Host "Pipeline Finished!" -ForegroundColor Magenta
