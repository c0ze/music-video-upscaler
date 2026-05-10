# Download Real-ESRGAN ncnn-vulkan model files into ..\models\.
#
# Idempotent: existing non-empty files are kept unless -Force is passed.
# Only requires built-in PowerShell cmdlets (Invoke-WebRequest, Expand-Archive).
#
# See ..\models\README.md for the catalogue and licensing notes.

[CmdletBinding()]
param(
    [switch]$BaseOnly,
    [switch]$NoGeneral,
    [switch]$Extras,
    [switch]$Force,
    [switch]$List,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
# TLS 1.2 is required for github.com on older PowerShell builds
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$WinDir    = $PSScriptRoot
$RepoRoot  = (Resolve-Path (Join-Path $WinDir "..")).Path
$ModelsDir = Join-Path $RepoRoot "models"

function Show-Usage {
    @"
Usage: .\windows\download-models.ps1 [options]

  (no args)      install base set + realesr-general-x4v3 (recommended)
  -BaseOnly      install only the xinntao bundled set
  -NoGeneral     skip realesr-general-x4v3 / -wdn-x4v3
  -Extras        additionally install community extras (4xLSDIR, 4xNomos8kSC)
  -Force         redownload even if files already exist
  -List          list models currently present in models\ and exit
  -Help          show this help and exit
"@ | Write-Host
}

if ($Help) { Show-Usage; exit 0 }

function Log     ($msg) { Write-Host "[models] $msg" }
function LogWarn ($msg) { Write-Warning "[models] $msg" }

function Get-PresentModels {
    if (-not (Test-Path $ModelsDir)) { return @() }
    Get-ChildItem -Path $ModelsDir -File -Filter "*.bin" -ErrorAction SilentlyContinue |
        ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.Name) } |
        Sort-Object -Unique
}

function Show-PresentModels {
    Log "models present in $ModelsDir :"
    $names = Get-PresentModels
    if ($names.Count -eq 0) {
        Write-Host "  (none)"
    } else {
        $names | ForEach-Object { Write-Host "  - $_" }
    }
}

if ($List) { Show-PresentModels; exit 0 }

New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

# Resolve flag combinations
$DoBase    = $true
$DoGeneral = -not $NoGeneral
$DoExtras  = $Extras.IsPresent
if ($BaseOnly) { $DoGeneral = $false; $DoExtras = $false }

function Get-File {
    param([string]$Url, [string]$Dest)
    if ((Test-Path $Dest) -and ((Get-Item $Dest).Length -gt 0) -and -not $Force) {
        return $false
    }
    $tmp = "$Dest.part"
    Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing
    Move-Item -Force -Path $tmp -Destination $Dest
    return $true
}

# ---------- base set: xinntao official ncnn-vulkan v0.2.5.0 zip ----------

$NcnnZipUrl = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"

$BaseModels = @(
    "realesrgan-x4plus",
    "realesrgan-x4plus-anime",
    "realesr-animevideov3-x2",
    "realesr-animevideov3-x3",
    "realesr-animevideov3-x4"
)

function Test-BaseAllPresent {
    foreach ($n in $BaseModels) {
        $bin   = Join-Path $ModelsDir "$n.bin"
        $param = Join-Path $ModelsDir "$n.param"
        if (-not ((Test-Path $bin)   -and (Get-Item $bin).Length   -gt 0)) { return $false }
        if (-not ((Test-Path $param) -and (Get-Item $param).Length -gt 0)) { return $false }
    }
    return $true
}

function Install-Base {
    if ((-not $Force) -and (Test-BaseAllPresent)) {
        Log "base models already present (use -Force to redownload)"
        return
    }
    Log "downloading xinntao Real-ESRGAN ncnn-vulkan v0.2.5.0"
    $tmp = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("rsr_models_" + [guid]::NewGuid().ToString("N"))) -Force
    try {
        $zipPath = Join-Path $tmp.FullName "r.zip"
        Get-File -Url $NcnnZipUrl -Dest $zipPath | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $tmp.FullName -Force
        $srcDir = Join-Path $tmp.FullName "models"
        foreach ($n in $BaseModels) {
            foreach ($ext in @("bin","param")) {
                $src = Join-Path $srcDir   "$n.$ext"
                $dst = Join-Path $ModelsDir "$n.$ext"
                if (-not (Test-Path $src)) {
                    LogWarn "missing in zip: $n.$ext"
                    continue
                }
                if ((Test-Path $dst) -and ((Get-Item $dst).Length -gt 0) -and -not $Force) {
                    Log "  keep    $n.$ext"
                    continue
                }
                Copy-Item -Force -Path $src -Destination $dst
                Log "  install $n.$ext"
            }
        }
    } finally {
        Remove-Item -Recurse -Force -Path $tmp.FullName -ErrorAction SilentlyContinue
    }
}

# ---------- realesr-general-x4v3 (community ncnn from upscayl) ------------

$UpscaylRaw = "https://raw.githubusercontent.com/upscayl/custom-models/main/models"

# logical_name -> upstream_basename
$GeneralMap = @{
    "realesr-general-x4v3"     = "RealESRGAN_General_x4_v3"
    "realesr-general-wdn-x4v3" = "RealESRGAN_General_WDN_x4_v3"
}

function Install-General {
    Log "downloading realesr-general-x4v3 from upscayl/custom-models"
    foreach ($dst in $GeneralMap.Keys) {
        $src = $GeneralMap[$dst]
        foreach ($ext in @("bin","param")) {
            $destFile = Join-Path $ModelsDir "$dst.$ext"
            if ((Test-Path $destFile) -and ((Get-Item $destFile).Length -gt 0) -and -not $Force) {
                Log "  keep    $dst.$ext"
                continue
            }
            Get-File -Url "$UpscaylRaw/$src.$ext" -Dest $destFile | Out-Null
            Log "  install $dst.$ext"
        }
    }
}

# ---------- optional extras ----------------------------------------------

$ExtraModels = @("4xLSDIR", "4xNomos8kSC")

function Install-Extras {
    Log "downloading community extras"
    foreach ($n in $ExtraModels) {
        foreach ($ext in @("bin","param")) {
            $destFile = Join-Path $ModelsDir "$n.$ext"
            if ((Test-Path $destFile) -and ((Get-Item $destFile).Length -gt 0) -and -not $Force) {
                Log "  keep    $n.$ext"
                continue
            }
            Get-File -Url "$UpscaylRaw/$n.$ext" -Dest $destFile | Out-Null
            Log "  install $n.$ext"
        }
    }
}

# ---------- verification --------------------------------------------------

function Test-Pairs {
    $orphans = 0
    Get-ChildItem -Path $ModelsDir -Filter "*.bin"   -ErrorAction SilentlyContinue | ForEach-Object {
        $param = [IO.Path]::ChangeExtension($_.FullName, ".param")
        if (-not (Test-Path $param)) {
            LogWarn "orphan .bin without .param: $($_.Name)"
            $orphans++
        }
    }
    Get-ChildItem -Path $ModelsDir -Filter "*.param" -ErrorAction SilentlyContinue | ForEach-Object {
        $bin = [IO.Path]::ChangeExtension($_.FullName, ".bin")
        if (-not (Test-Path $bin)) {
            LogWarn "orphan .param without .bin: $($_.Name)"
            $orphans++
        }
    }
    return ($orphans -eq 0)
}

# ---------- main ----------------------------------------------------------

if ($DoBase)    { Install-Base }
if ($DoGeneral) { Install-General }
if ($DoExtras)  { Install-Extras }

if (Test-Pairs) {
    Log "all model files have matching .bin/.param pairs"
}

Log "done"
Show-PresentModels
