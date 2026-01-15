param(
    [int]$TargetFrames = 8668,
    [string]$Directory = "c:\music_videos\pestilence\tmp_upscaled_2x"
)

Write-Host "Monitoring Upscale Progress..." -ForegroundColor Cyan
Write-Host "Target: $TargetFrames frames"
Write-Host "Monitoring: $Directory"
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

$lastCount = 0
$startTime = Get-Date

while ($true) {
    if (Test-Path $Directory) {
        $count = (Get-ChildItem $Directory -Filter "*.png").Count
        $percent = [math]::Round(($count / $TargetFrames) * 100, 2)
        
        # Calculate speed (frames per minute) over the last interval
        # Ideally we'd smooth this, but simple is fine.
        
        $timestamp = Get-Date
        Write-Host "[$($timestamp.ToString('HH:mm:ss'))] Frames: $count / $TargetFrames ($percent%)" -ForegroundColor Green
        
        if ($count -ge $TargetFrames) {
            Write-Host "Upscale Complete!" -ForegroundColor Magenta
            break
        }
    }
    else {
        Write-Host "Directory not found yet..." -ForegroundColor Red
    }
    
    Start-Sleep -Seconds 30
}
