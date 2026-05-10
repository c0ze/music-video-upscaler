
param(
    [Parameter(Mandatory = $true)]
    [string]$InputVideo,
    [Parameter(Mandatory = $true)]
    [string]$InputAudio,
    [string]$YouTubeUrl
)

$WinDir = $PSScriptRoot
$YtDlpExe = Join-Path $WinDir "yt-dlp.exe"

# Setup paths
$videoPath = Convert-Path $InputVideo
$audioPath = Convert-Path $InputAudio
$videoDir = Split-Path -Parent $videoPath
$videoBase = [System.IO.Path]::GetFileNameWithoutExtension($videoPath)
$syncedAudio = Join-Path $videoDir "${videoBase}_synced.flac"
$ytAudio = Join-Path $videoDir "${videoBase}_youtube_audio.wav"

Write-Host "Syncing Audio..." -ForegroundColor Cyan
Write-Host "Video: $videoPath"
Write-Host "Audio: $audioPath"

# Download YT if needed
if ($YouTubeUrl -and -not (Test-Path $ytAudio)) {
    Write-Host "Downloading YouTube audio..."
    & $YtDlpExe -x --audio-format wav -o $ytAudio "$YouTubeUrl" 2>&1 | Out-Null
}

$videoSilence = 0.0
$flacSilence = 0.0

# Helper to detect silence
function Get-SilenceStart($file) {
    if (-not (Test-Path $file)) { return 0.0 }
    $res = & ffmpeg -i $file -t 5 -af "silencedetect=n=-50dB:d=0.01" -f null - 2>&1
    if ($res -match "silence_end:\s*([\d.]+)") { return [double]$matches[1] }
    return 0.0
}

# Use YT audio for video ref if avail, else video track
if (Test-Path $ytAudio) {
    $videoSilence = Get-SilenceStart $ytAudio
}
else {
    $videoSilence = Get-SilenceStart $videoPath
}

$flacSilence = Get-SilenceStart $audioPath
$addSilence = $videoSilence - $flacSilence

Write-Host "Video Silence: $videoSilence s"
Write-Host "FLAC Silence:  $flacSilence s"
Write-Host "Offset:        $addSilence s"

if ($addSilence -gt 0.01) {
    Write-Host "Adding silence to FLAC..." -ForegroundColor Yellow
    # Native ffmpeg concat
    & ffmpeg -y -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=44100" -t $addSilence -i $audioPath -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1[out]" -map "[out]" -c:a flac $syncedAudio 2>&1 | Out-Null
    Write-Host "Created: $syncedAudio" -ForegroundColor Green
}
else {
    Write-Host "No silence needed. Copying original." -ForegroundColor Green
    Copy-Item $audioPath $syncedAudio -Force
}
