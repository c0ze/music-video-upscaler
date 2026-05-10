# Windows workflow

PowerShell pipeline preserved verbatim from the original project. All scripts
resolve sibling files via `$PSScriptRoot` and use the **repository root** as the
working directory when invoking Real-ESRGAN so that `..\models` resolves
correctly.

## Required binaries (place in this folder)

| File | Source | Notes |
|------|--------|-------|
| `realesrgan-ncnn-vulkan.exe` | https://github.com/xinntao/Real-ESRGAN/releases | Vulkan upscaler. Keep `vcomp140.dll` and `vcomp140d.dll` next to it. |
| `vcomp140.dll`, `vcomp140d.dll` | shipped with Visual C++ runtime / Real-ESRGAN release zip | OpenMP runtime required by the upscaler. |
| `yt-dlp.exe` *(optional)* | https://github.com/yt-dlp/yt-dlp/releases | Used by `01_sync_audio.ps1`/`upscale_video.ps1` when a YouTube URL is provided; falls back to PATH `yt-dlp` if absent here. |

`models/` lives at the repository root (one level up from this folder) and is
shared with the POSIX workflow.

## Install dependencies

```powershell
.\install-dependencies.ps1
```

Installs FFmpeg via `winget` (or `choco`) and `yt-dlp` via `pip` when missing.
Real-ESRGAN itself is not auto-downloaded for Windows — drop the portable build
into this folder.

## Pipelines

Full automated pipeline on a folder containing one source video and one source FLAC/WAV:

```powershell
.\run_pipeline.ps1 -TargetFolder ..\artist_folder -YouTubeUrl "https://www.youtube.com/watch?v=..." -Scale 4
```

Manual stages (run from anywhere, paths can be relative):

```powershell
.\00_sanitize.ps1 -Directory ..\artist
.\01_sync_audio.ps1 -InputVideo ..\artist\song.mp4 -InputAudio ..\artist\song.flac -YouTubeUrl "https://..."
.\02_extract.ps1 -InputVideo ..\artist\song.mp4 -OutputFramesDir ..\artist\tmp_frames
.\03_upscale.ps1 -InputFramesDir ..\artist\tmp_frames -OutputUpscaledDir ..\artist\tmp_upscaled_4x -Scale 4 -Model realesr-general-x4v3
.\04_mux.ps1 -FramesDir ..\artist\tmp_upscaled_4x -AudioPath ..\artist\song_synced.flac -OriginalVideo ..\artist\song.mp4 -OutputVideo ..\output\song_HQ.mkv
```

Standalone, full-featured driver:

```powershell
.\upscale_video.ps1 -InputVideo "..\artist\video.mp4" -InputAudio "..\artist\audio.flac" -Scale 4 -OutputFormat mkv -YouTubeUrl "https://..."
# Defaults to -Model realesr-general-x4v3. Override with -Model realesr-general-wdn-x4v3 for very noisy 240p–360p sources.
```

Progress monitor (separate console):

```powershell
.\monitor_progress.ps1 -TargetFrames 8000 -Directory "..\artist\tmp_upscaled_4x"
```

## Models

Pass any model name from `..\models\*.param` via `-Model`:

- **`realesr-general-x4v3`** *(default)* — best for compressed YouTube sources
- `realesr-general-wdn-x4v3` — same architecture, stronger denoising (240p–360p)
- `realesrgan-x4plus` — only for genuinely clean 720p / 1080p sources
- `realesrgan-x4plus-anime` — anime stills, 4×
- `realesr-animevideov3` — anime/animation video, supports `-Scale 2/3/4`
- (drop additional `.bin/.param` pairs into `..\models\` to extend)

The standalone Real-ESRGAN ncnn-vulkan binary does **not** support the `-dn`
denoise flag (Python-only). Switch the model name to control denoise strength.

See `..\models\README.md` for the full catalogue and `..\docs\upscalers-2026.md`
for higher-quality alternatives that work on Windows (FlashVSR, SeedVR2,
Real-CUGAN, waifu2x).
