
param(
    [Parameter(Mandatory = $true)]
    [string]$Directory
)

$absPath = Convert-Path -LiteralPath $Directory
Write-Host "Sanitizing files in: $absPath" -ForegroundColor Cyan

Get-ChildItem -Path $absPath | ForEach-Object {
    $originalName = $_.Name
    # Lowercase, parens/brackets to underscores
    $newName = $originalName.ToLower() -replace '[\[\]\(\)\s''"]', '_' 
    # Remove duplicate underscores
    $newName = $newName -replace '_+', '_'
    # Trim leading/trailing underscores
    $newName = $newName -replace '^_|_$', ''
    # Specific fix: Ensure extension dot isn't messed up if it matched regex (it shouldn't) but clean up before extension
    
    if ($originalName -cne $newName) {
        $newFullPath = Join-Path $absPath $newName
        Write-Host "Renaming: '$originalName' -> '$newName'"
        Rename-Item -LiteralPath $_.FullName -NewName $newName -Force
    }
}
Write-Host "Sanitization Complete" -ForegroundColor Green
