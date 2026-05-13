<#
.SYNOPSIS
    Upscale a video using Real-ESRGAN and combine with high-quality audio.

.DESCRIPTION
    This script:
    1. Detects and syncs audio timing (adds silence to FLAC if needed)
    2. Extracts frames from the input video at native framerate
    3. Upscales each frame using Real-ESRGAN
    4. Reassembles frames into a video with the synced high-quality audio

.PARAMETER Scale
    Upscale factor: 2 or 4 (default: 4)

.PARAMETER OutputFormat
    Output format: mp4 or mkv (default: mkv)
    MKV supports lossless FLAC audio, MP4 uses AAC.

.PARAMETER InputVideo
    Filename of the input video (relative to source folder or absolute)

.PARAMETER InputAudio
    Filename of the input audio (relative to source folder or absolute)

.PARAMETER YouTubeUrl
    Optional YouTube URL to download audio for sync detection.
    If not provided, uses existing cached audio or analyzes video audio track.

.PARAMETER SkipExtract
    Skip frame extraction if frames already exist

.PARAMETER SkipUpscale
    Skip upscaling if upscaled frames already exist

.PARAMETER SkipAudioSync
    Skip audio sync detection and adjustment

.EXAMPLE
    .\upscale_video.ps1 -InputVideo "video.mp4" -InputAudio "audio.flac" -YouTubeUrl "https://youtube.com/watch?v=xxx"
#>

param(
    [ValidateSet(2, 4)]
    [int]$Scale = 4,

    [ValidateSet("mp4", "mkv")]
    [string]$OutputFormat = "mkv",

    [Parameter(Mandatory = $true)]
    [string]$InputVideo,

    [Parameter(Mandatory = $true)]
    [string]$InputAudio,

    [Parameter(Mandatory = $false)]
    [ValidateSet(
        "realesr-general-x4v3",
        "realesr-general-wdn-x4v3",
        "realesrgan-x4plus",
        "realesrgan-x4plus-anime",
        "realesrnet-x4plus",
        "realesr-animevideov3"
    )]
    [string]$Model = "realesr-general-x4v3",

    [Parameter(Mandatory = $false)]
    [string]$YouTubeUrl = "",

    [switch]$SkipExtract,
    [switch]$SkipUpscale,
    [switch]$SkipAudioSync
)

Write-Host "DEBUG: Script loaded successfully" -ForegroundColor DarkGray

# ============================================================================
# CONFIGURATION
# ============================================================================
$WinDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $WinDir

# ============================================================================
# PATHS (auto-configured)
# ============================================================================

if ([System.IO.Path]::IsPathRooted($InputVideo)) {
    $InputVideoPath = $InputVideo
}
else {
    $tryCwd = Join-Path (Get-Location) $InputVideo
    $tryRepo = Join-Path $RepoRoot $InputVideo
    if (Test-Path -LiteralPath $tryCwd) {
        $InputVideoPath = [System.IO.Path]::GetFullPath($tryCwd)
    }
    elseif (Test-Path -LiteralPath $tryRepo) {
        $InputVideoPath = [System.IO.Path]::GetFullPath($tryRepo)
    }
    else {
        $InputVideoPath = [System.IO.Path]::GetFullPath($InputVideo)
    }
}

if ([System.IO.Path]::IsPathRooted($InputAudio)) {
    $InputAudioPath = $InputAudio
}
else {
    $tryCwd = Join-Path (Get-Location) $InputAudio
    $srcGuess = Split-Path -Parent $InputVideoPath
    $trySrc = Join-Path $srcGuess $InputAudio
    $tryRepo = Join-Path $RepoRoot $InputAudio
    if (Test-Path -LiteralPath $tryCwd) {
        $InputAudioPath = [System.IO.Path]::GetFullPath($tryCwd)
    }
    elseif (Test-Path -LiteralPath $trySrc) {
        $InputAudioPath = [System.IO.Path]::GetFullPath($trySrc)
    }
    elseif (Test-Path -LiteralPath $tryRepo) {
        $InputAudioPath = [System.IO.Path]::GetFullPath($tryRepo)
    }
    else {
        $InputAudioPath = [System.IO.Path]::GetFullPath($InputAudio)
    }
}

$VideoBaseName = [System.IO.Path]::GetFileNameWithoutExtension($InputVideoPath)
$Engine = "realesrgan"
$OutputName = "${VideoBaseName}_${Engine}_${Model}_${Scale}x_HQ"

$SourceDir = Split-Path -Parent $InputVideoPath
if (-not $SourceDir) { $SourceDir = $RepoRoot }

$RealESRGAN = Join-Path $WinDir "realesrgan-ncnn-vulkan.exe"
$YtDlp = Join-Path $WinDir "yt-dlp.exe"

$FramesDir = Join-Path $SourceDir "tmp_frames"
$UpscaledDir = Join-Path $SourceDir "tmp_upscaled_${Scale}x"
$OutputDir = Join-Path $SourceDir "output"
$OutputVideo = Join-Path $OutputDir "${OutputName}.${OutputFormat}"

# ============================================================================
# VALIDATION
# ============================================================================

# Check input files exist
if (-not (Test-Path -LiteralPath $InputVideoPath)) {
    Write-Host "ERROR: Input video not found: $InputVideoPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $InputAudioPath)) {
    Write-Host "ERROR: Input audio not found: $InputAudioPath" -ForegroundColor Red
    exit 1
}

# Check upscaler exists
Write-Host "Checking for upscaler at: $RealESRGAN" -ForegroundColor Gray
if (-not (Test-Path -LiteralPath $RealESRGAN)) {
    Write-Host "ERROR: Real-ESRGAN not found at: $RealESRGAN" -ForegroundColor Red
    exit 1
}

# Get native framerate from source video
Write-Host "Detecting native framerate..." -ForegroundColor DarkGray
$frameRateStr = & ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$InputVideoPath" 2>&1
$FrameRate = $frameRateStr.Trim()
Write-Host "  Native framerate: $FrameRate" -ForegroundColor DarkGray

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Video Upscaling with Real-ESRGAN" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Input Video:  $InputVideoPath"
Write-Host "  Input Audio:  $InputAudioPath"
Write-Host "  Scale:        ${Scale}x"
Write-Host "  Framerate:    $FrameRate (native)"
Write-Host "  Model:        $Model"
Write-Host "  Format:       $OutputFormat"
Write-Host "  Output:       $OutputVideo"
Write-Host ""

# Create directories
New-Item -ItemType Directory -Force -Path $FramesDir | Out-Null
New-Item -ItemType Directory -Force -Path $UpscaledDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# ============================================================================
# AUDIO SYNC DETECTION
# ============================================================================
$SyncedAudioPath = $InputAudioPath

if (-not $SkipAudioSync) {
    Write-Host ""
    Write-Host "Audio Sync Detection..." -ForegroundColor Green
    
    # Get video duration
    $videoDuration = & ffprobe -v error -show_entries format=duration -of csv=p=0 "$InputVideoPath" 2>&1
    $videoDuration = [double]$videoDuration.Trim()
    Write-Host "  Video duration: $([math]::Round($videoDuration, 2))s" -ForegroundColor DarkGray
    
    # Get FLAC duration
    $flacDuration = & ffprobe -v error -show_entries format=duration -of csv=p=0 "$InputAudioPath" 2>&1
    $flacDuration = [double]$flacDuration.Trim()
    Write-Host "  FLAC duration:  $([math]::Round($flacDuration, 2))s" -ForegroundColor DarkGray
    
    # Check for existing YouTube audio or download if URL provided
    $ytAudioPath = Join-Path $SourceDir "${VideoBaseName}_youtube_audio.wav"
    
    if (Test-Path -LiteralPath $ytAudioPath) {
        Write-Host "  Using existing YouTube audio: $ytAudioPath" -ForegroundColor DarkGray
    }
    elseif ($YouTubeUrl -ne "") {
        Write-Host "  Downloading YouTube audio..." -ForegroundColor DarkGray
        & $YtDlp -x --audio-format wav -o "$ytAudioPath" "$YouTubeUrl" 2>&1 | Out-Null
        if (-not (Test-Path -LiteralPath $ytAudioPath)) {
            Write-Host "  WARNING: Failed to download YouTube audio. Skipping sync." -ForegroundColor Yellow
            $ytAudioPath = ""
        }
    }
    else {
        Write-Host "  No YouTube URL provided and no cached audio found." -ForegroundColor DarkGray
        Write-Host "  Analyzing video audio track for silence..." -ForegroundColor DarkGray
        $ytAudioPath = ""
    }
    
    # Detect silence at start of video/YouTube audio
    $videoSilenceEnd = 0.0
    if ($ytAudioPath -ne "" -and (Test-Path -LiteralPath $ytAudioPath)) {
        # Analyze YouTube audio for silence
        $silenceOutput = & ffmpeg -i "$ytAudioPath" -t 5 -af "silencedetect=n=-50dB:d=0.01" -f null - 2>&1
        $silenceMatch = [regex]::Match($silenceOutput, "silence_end:\s*([\d.]+)")
        if ($silenceMatch.Success) {
            $videoSilenceEnd = [double]$silenceMatch.Groups[1].Value
        }
    }
    else {
        # Analyze video audio track directly
        $silenceOutput = & ffmpeg -i "$InputVideoPath" -t 5 -af "silencedetect=n=-50dB:d=0.01" -f null - 2>&1
        $silenceMatch = [regex]::Match($silenceOutput, "silence_end:\s*([\d.]+)")
        if ($silenceMatch.Success) {
            $videoSilenceEnd = [double]$silenceMatch.Groups[1].Value
        }
    }
    Write-Host "  Video audio starts at: $([math]::Round($videoSilenceEnd, 3))s" -ForegroundColor DarkGray
    
    # Detect silence at start of FLAC
    $flacSilenceEnd = 0.0
    $flacSilenceOutput = & ffmpeg -i "$InputAudioPath" -t 5 -af "silencedetect=n=-50dB:d=0.01" -f null - 2>&1
    $flacSilenceMatch = [regex]::Match($flacSilenceOutput, "silence_end:\s*([\d.]+)")
    if ($flacSilenceMatch.Success) {
        $flacSilenceEnd = [double]$flacSilenceMatch.Groups[1].Value
    }
    Write-Host "  FLAC audio starts at:  $([math]::Round($flacSilenceEnd, 3))s" -ForegroundColor DarkGray
    
    # Calculate offset needed
    $silenceToAdd = $videoSilenceEnd - $flacSilenceEnd
    
    if ($silenceToAdd -gt 0.01) {
        Write-Host "  Adding $([math]::Round($silenceToAdd, 3))s silence to FLAC start..." -ForegroundColor Yellow
        
        $SyncedAudioPath = Join-Path $SourceDir "${VideoBaseName}_synced.flac"
        
        # Native ffmpeg command with single-quoted complex filter
        & ffmpeg -y -f lavfi -t $silenceToAdd -i "anullsrc=channel_layout=stereo:sample_rate=44100" -i "$InputAudioPath" -filter_complex '[0:a][1:a]concat=n=2:v=0:a=1[out]' -map '[out]' -c:a flac "$SyncedAudioPath" 2>&1 | Out-Null
        
        if (Test-Path -LiteralPath $SyncedAudioPath) {
            Write-Host "  Created synced audio: $SyncedAudioPath" -ForegroundColor Green
        }
        else {
            Write-Host "  WARNING: Failed to create synced audio. Using original." -ForegroundColor Yellow
            $SyncedAudioPath = $InputAudioPath
        }
    }
    elseif ($silenceToAdd -lt -0.01) {
        Write-Host "  FLAC has more silence than video ($([math]::Round(-$silenceToAdd, 3))s extra)" -ForegroundColor DarkGray
        Write-Host "  No adjustment needed (FLAC starts later)" -ForegroundColor DarkGray
    }
    else {
        Write-Host "  Audio timing already matched" -ForegroundColor Green
    }
    
    # Duration mismatch warning
    $durationDiff = [math]::Abs($flacDuration - $videoDuration)
    if ($durationDiff -gt 1.0) {
        Write-Host ""
        Write-Host "  ╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
        Write-Host "  ║  WARNING: Audio/Video duration mismatch!                       ║" -ForegroundColor Yellow
        Write-Host "  ║  Video: $([math]::Round($videoDuration, 2))s  |  FLAC: $([math]::Round($flacDuration, 2))s  |  Diff: $([math]::Round($durationDiff, 2))s" -ForegroundColor Yellow
        Write-Host "  ║  The video may have edited/cut sections. Manual sync needed.   ║" -ForegroundColor Yellow
        Write-Host "  ╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
        Write-Host ""
    }
}
else {
    Write-Host ""
    Write-Host "Audio Sync: Skipped" -ForegroundColor Yellow
}

# ============================================================================
# STEP 1: Extract Frames
# ============================================================================
Write-Host "Step 1/3: Extracting frames at native framerate..." -ForegroundColor Green

if ($SkipExtract) {
    Write-Host "  Skipped (using existing frames)" -ForegroundColor Yellow
}
else {
    # Clean existing frames
    Remove-Item -Path "$FramesDir\*" -Force -ErrorAction SilentlyContinue
    
    Write-Host "  Running ffmpeg to extract frames..." -ForegroundColor DarkGray
    $startTime = Get-Date
    
    # Extract at native framerate
    & ffmpeg -i "$InputVideoPath" -f image2 "$FramesDir\%06d.png" 2>&1 | Out-Null
    
    $elapsed = (Get-Date) - $startTime
    $frameCount = (Get-ChildItem -Path $FramesDir -Filter "*.png").Count
    Write-Host "  Extracted $frameCount frames in $([math]::Round($elapsed.TotalSeconds, 1))s" -ForegroundColor Green
}

# Count frames
$frameCount = (Get-ChildItem -Path $FramesDir -Filter "*.png").Count
Write-Host "  Total frames to process: $frameCount" -ForegroundColor Cyan

# ============================================================================
# STEP 2: Upscale Frames
# ============================================================================
Write-Host ""
Write-Host "Step 2/3: Upscaling frames with Real-ESRGAN (${Scale}x)..." -ForegroundColor Green
Write-Host "  This may take a while depending on your GPU..." -ForegroundColor Yellow

if ($SkipUpscale) {
    Write-Host "  Skipped (using existing upscaled frames)" -ForegroundColor Yellow
}
else {
    # Clean existing upscaled frames
    Remove-Item -Path "$UpscaledDir\*" -Force -ErrorAction SilentlyContinue
    
    $startTime = Get-Date
    
    Write-Host "  Using Real-ESRGAN with $Model model..." -ForegroundColor DarkGray
    Push-Location $RepoRoot
    try {
        & $RealESRGAN -i "$FramesDir" -o "$UpscaledDir" -n $Model -s $Scale -f png
    }
    finally {
        Pop-Location
    }
    
    $elapsed = (Get-Date) - $startTime
    $upscaledCount = (Get-ChildItem -Path $UpscaledDir -Filter "*.png").Count
    Write-Host "  Upscaled $upscaledCount frames in $([math]::Round($elapsed.TotalMinutes, 1)) minutes" -ForegroundColor Green
    
    if ($upscaledCount -ne $frameCount) {
        Write-Host "  WARNING: Frame count mismatch! Expected $frameCount, got $upscaledCount" -ForegroundColor Yellow
    }
}

# ============================================================================
# STEP 3: Reassemble Video with Audio
# ============================================================================
Write-Host ""
Write-Host "Step 3/3: Reassembling video with high-quality audio..." -ForegroundColor Green

# Remove existing output
if (Test-Path -LiteralPath $OutputVideo) {
    Remove-Item -LiteralPath $OutputVideo -Force
}

$startTime = Get-Date

if ($OutputFormat -eq "mkv") {
    Write-Host "  Output: MKV with copied audio stream (FLAC)" -ForegroundColor DarkGray
    Write-Host "  Audio source: $SyncedAudioPath" -ForegroundColor DarkGray
    & ffmpeg -framerate $FrameRate -i "$UpscaledDir\%06d.png" -i "$SyncedAudioPath" -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -map 0:v:0 -map 1:a:0 "$OutputVideo"
}
else {
    Write-Host "  Output: MP4 with AAC 320kbps audio" -ForegroundColor DarkGray
    Write-Host "  Audio source: $SyncedAudioPath" -ForegroundColor DarkGray
    & ffmpeg -framerate $FrameRate -i "$UpscaledDir\%06d.png" -i "$SyncedAudioPath" -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a aac -b:a 320k -map 0:v:0 -map 1:a:0 -shortest "$OutputVideo"
}

$elapsed = (Get-Date) - $startTime

# ============================================================================
# COMPLETE
# ============================================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  COMPLETE!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path -LiteralPath $OutputVideo) {
    $outputSize = [math]::Round((Get-Item -LiteralPath $OutputVideo).Length / 1MB, 1)
    Write-Host "Output file: $OutputVideo" -ForegroundColor Green
    Write-Host "File size:   ${outputSize} MB" -ForegroundColor Green
    
    # Get video info
    $videoInfo = & ffprobe -v error -select_streams v:0 -show_entries stream=width, height, duration -of csv=p=0 "$OutputVideo" 2>&1
    if ($videoInfo) {
        $parts = $videoInfo.ToString().Split(',')
        if ($parts.Count -ge 2) {
            Write-Host "Resolution:  $($parts[0])x$($parts[1])" -ForegroundColor Green
        }
    }
}
else {
    Write-Host "ERROR: Output file was not created!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Encoding took $([math]::Round($elapsed.TotalMinutes, 1)) minutes" -ForegroundColor Cyan
