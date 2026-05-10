
param(
    [Parameter(Mandatory = $true)]
    [string]$InputFramesDir,
    [string]$OutputUpscaledDir,
    [int]$Scale = 4,
    [string]$Model = "realesr-general-x4v3"
)

$WinDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $WinDir
$RealESRGANExe = Join-Path $WinDir "realesrgan-ncnn-vulkan.exe"

if (-not $OutputUpscaledDir) {
    # Default sibling dir
    $parent = Split-Path -Parent (Convert-Path $InputFramesDir)
    $OutputUpscaledDir = Join-Path $parent "tmp_upscaled_${Scale}x"
}

# Ensure output dir exists (do not wipe)
if (-not (Test-Path $OutputUpscaledDir)) {
    New-Item -ItemType Directory -Force -Path $OutputUpscaledDir | Out-Null
}

# Identify frames that need upscaling
$allFrames = Get-ChildItem -Path "$InputFramesDir\*.png"
$existingUpscaled = Get-ChildItem -Path "$OutputUpscaledDir\*.png"
$existingNames = $existingUpscaled.Name

# Simple diff by name
$todoFrames = $allFrames | Where-Object { $existingNames -notcontains $_.Name }

if ($todoFrames.Count -eq 0) {
    Write-Host "All frames already upscaled." -ForegroundColor Green
}
else {
    Write-Host "Found $($todoFrames.Count) frames to upscale (skipping $($existingUpscaled.Count))." -ForegroundColor Cyan
    
    # Create temp input dir for batch
    $batchDir = Join-Path (Split-Path -Parent $InputFramesDir) "tmp_frames_batch"
    if (Test-Path $batchDir) { Remove-Item $batchDir -Recurse -Force }
    New-Item -ItemType Directory -Path $batchDir | Out-Null
    
    # Copy todo frames
    foreach ($f in $todoFrames) {
        Copy-Item $f.FullName -Destination $batchDir
    }
    
    # Run upscale on batch dir (models live under repo ./models)
    Write-Host "Running RealESRGAN on batch..."
    Write-Host "Model: $Model (x$Scale)"
    Push-Location $RepoRoot
    try {
        & $RealESRGANExe -i $batchDir -o $OutputUpscaledDir -n $Model -s $Scale -f png
    }
    finally {
        Pop-Location
    }
    
    # Clean batch dir
    Remove-Item $batchDir -Recurse -Force
}

Write-Host "Upscale Complete" -ForegroundColor Green
