# Music Video Upscaler

AI-powered video upscaling pipeline for high-quality music videos with lossless audio.

This project takes music videos (often from YouTube), upscales them with Real-ESRGAN (NCNN/Vulkan), and muxes them with lossless FLAC audio from CD or studio sources.

---

## Platforms

| Platform | Workflow | Entry scripts |
|----------|----------|----------------|
| **Linux / macOS** | POSIX Bash from repository root | `./run_pipeline.sh`, `./upscale_video.sh`, `./install-dependencies.sh` |
| **Windows** | PowerShell in `windows/` | `windows\run_pipeline.ps1`, `windows\upscale_video.ps1`, `windows\install-dependencies.ps1` |

On Windows you can also run `./install-dependencies.sh` from **Git Bash** or MSYS2 for the same installer logic as Unix.

Shared assets:

- `models/` — Real-ESRGAN weights (used by both workflows; the Vulkan binary resolves models relative to the **repository root** working directory).
- `METAL_VIDS_UPSCALED_FLAC/` — default final release output tree.

---

## Features

- **AI upscaling**: Real-ESRGAN (NCNN/Vulkan), 2× or 4×
- **Lossless audio**: Replace compressed web audio with FLAC (or AAC for MP4)
- **Automatic audio sync**: Silence detection + optional YouTube audio grab via yt-dlp
- **GPU accelerated**: Vulkan inference on NVIDIA / AMD / Intel where drivers allow

---

## Dependencies

| Tool | Role |
|------|------|
| **ffmpeg** / **ffprobe** | Frames, filters, mux |
| **yt-dlp** | Optional YouTube audio for sync |
| **realesrgan-ncnn-vulkan** | Frame upscaling (Vulkan) |

### Platform-agnostic install (recommended)

From the repository root:

```bash
chmod +x install-dependencies.sh   # once
./install-dependencies.sh
```

Optional: download a Linux x86_64 Vulkan binary into `tools/` automatically:

```bash
INSTALL_REALESRGAN=1 ./install-dependencies.sh
```

The installer detects macOS (Homebrew), Debian/Ubuntu, Fedora, Arch, and Git Bash/MSYS on Windows (`winget`/`choco` + `pip`).

### Windows (native PowerShell)

```powershell
cd windows
.\install-dependencies.ps1
```

Place portable binaries next to the scripts when not using Linux auto-download:

- `windows\realesrgan-ncnn-vulkan.exe`
- `windows\yt-dlp.exe` (optional if `yt-dlp` is on `PATH`)

Vulkan/OpenMP support files (`vcomp140.dll`, etc.) stay alongside `realesrgan-ncnn-vulkan.exe` per upstream docs.

### Verify

```bash
ffmpeg -version
ffprobe -version
yt-dlp --version
# Linux/macOS after INSTALL_REALESRGAN=1 or manual install:
./tools/realesrgan-ncnn-vulkan -h
```

Override the upscaler location on Unix:

```bash
export REALESRGAN_BIN=/path/to/realesrgan-ncnn-vulkan
```

### Models

The repository ships seven Real-ESRGAN ncnn models in `models/`, including
**`realesr-general-x4v3`** (the new pipeline default, best for noisy YouTube
sources) and its `-wdn` variant for stronger denoising. To re-fetch / verify or
add community extras:

```bash
./download_models.sh                # base + realesr-general-x4v3 (idempotent)
./download_models.sh --extras       # also fetch community extras
./download_models.sh --list

# Windows
.\windows\download-models.ps1
```

Full catalogue, URLs, and licensing notes: [`models/README.md`](models/README.md).

---

## Usage (Linux / macOS)

Full pipeline on a folder containing one primary video and one primary FLAC/WAV:

```bash
./run_pipeline.sh ./artist_folder "https://www.youtube.com/watch?v=..." 4
```

Manual steps:

```bash
./00_sanitize.sh ./artist
./01_sync_audio.sh ./artist/song.mp4 ./artist/song.flac "https://..."
./02_extract.sh ./artist/song.mp4 ./artist/tmp_frames
./03_upscale.sh ./artist/tmp_frames ./artist/tmp_upscaled_4x 4 realesr-general-x4v3
./04_mux.sh ./artist/tmp_upscaled_4x ./artist/song_synced.flac ./output.mkv ./artist/song.mp4
```

Standalone orchestrator:

```bash
./upscale_video.sh ./artist/video.mp4 ./artist/audio.flac "https://..."
# Optional env:
#   SCALE=4 OUTPUT_FORMAT=mkv SKIP_EXTRACT=1
#   MODEL=realesr-general-x4v3      (default — best for noisy YouTube)
#   MODEL=realesr-general-wdn-x4v3  (stronger denoise for very noisy 240p/360p)
#   MODEL=realesrgan-x4plus         (only for already-clean 720p/1080p sources)
```

Monitor progress (another terminal):

```bash
./monitor_progress.sh 8000 ./artist/tmp_upscaled_4x
```

---

## Usage (Windows)

Run from the repo root or `windows`; scripts invoke siblings via `$PSScriptRoot`.

Full pipeline:

```powershell
.\windows\run_pipeline.ps1 -TargetFolder .\artist_folder -YouTubeUrl "https://www.youtube.com/watch?v=..." -Scale 4
```

Standalone:

```powershell
.\windows\upscale_video.ps1 -InputVideo ".\artist\video.mp4" -InputAudio ".\artist\audio.flac" -YouTubeUrl "https://..."
```

Progress:

```powershell
.\windows\monitor_progress.ps1 -TargetFrames 8000 -Directory ".\artist\tmp_upscaled_4x"
```

---

## Upscaling guidelines

The pipeline default is **`realesr-general-x4v3`** — it handles real-world
YouTube degradation (re-encoding, mosquito noise, blocky compression) much
better than `realesrgan-x4plus` and won't over-sharpen halos around stage
lighting or drum kits.

| Source resolution      | Scale | Recommended model              | Notes                                                                 |
|------------------------|-------|--------------------------------|-----------------------------------------------------------------------|
| 240p–360p (very noisy) | 4×    | `realesr-general-wdn-x4v3`     | "WDN" twin = stronger denoising                                       |
| 480p typical YouTube   | 4×    | `realesr-general-x4v3` *(default)* | Best general model for compressed sources                          |
| 720p / 1080p clean     | 2×–4× | `realesr-general-x4v3` *(default)* or `realesrgan-x4plus` | `x4plus` only when source is genuinely clean |
| Anime / animated       | 2×–4× | `realesr-animevideov3`         | Bundled video model with native 2×/3×/4× variants                     |

Pass a non-default with `MODEL=… ./upscale_video.sh` (POSIX) or
`-Model …` (PowerShell). Models shipped under `models/` match `-n` names
passed to Real-ESRGAN.

> Note: the standalone ncnn-vulkan binary does **not** accept `-dn` (that flag
> only exists in the upstream Python `inference_realesrgan.py`). On ncnn you
> control denoise strength by switching between `realesr-general-x4v3`
> (preserves more texture) and `realesr-general-wdn-x4v3` (max denoise).

For an in-depth comparison of newer models (FlashVSR, SeedVR2, RealBasicVSR,
Real-CUGAN, waifu2x, APISR, PiperSR/CoreML on Apple Silicon, ROCm on
RDNA4 AMD GPUs) and recommendations per source quality and target hardware,
see [`docs/upscalers-2026.md`](docs/upscalers-2026.md).

The Windows-specific commands and required `.exe` filenames live in
[`windows/README.md`](windows/README.md).

---

## Project layout

```
music-video-upscaler/
├── install-dependencies.sh      # Unix / Git Bash installer
├── models/
├── tools/                         # Downloaded Linux binary / optional yt-dlp shim
├── windows/
│   ├── install-dependencies.ps1
│   ├── run_pipeline.ps1
│   ├── upscale_video.ps1
│   ├── 00_sanitize.ps1 … 04_mux.ps1
│   ├── monitor_progress.ps1
│   └── (realesrgan-ncnn-vulkan.exe, yt-dlp.exe — user-supplied on Windows)
├── 00_sanitize.sh … 04_mux.sh   # POSIX equivalents
├── run_pipeline.sh
├── upscale_video.sh
├── monitor_progress.sh
├── lib/
│   └── pipeline.sh               # Shared bash helpers
├── METAL_VIDS_UPSCALED_FLAC/    # Output root (created by pipeline)
└── README.md
```

---

## Output

Default releases land under `METAL_VIDS_UPSCALED_FLAC/<folder_name>/`:

- **Container**: MKV (or MP4 when requested)
- **Video**: H.264 / libx264, CRF 18, `slow`
- **Audio**: FLAC copied (`mkv`) or AAC (`mp4`)

---

## Troubleshooting

### ffmpeg / ffprobe not found

Install via `./install-dependencies.sh` or your OS package manager; ensure the install location is on `PATH`.

### Real-ESRGAN cannot load models

Upscaler cwd must see `./models` at the **repository root**. POSIX scripts `cd` there before invoking the binary; Windows PowerShell uses `Push-Location $RepoRoot` around Real-ESRGAN.

### Vulkan / GPU issues

Update GPU drivers. Try `-g 0` style GPU selection only if your build supports it.

### Audio sync drift

Large duration mismatch warnings indicate edits/cuts between video and album audio — manual alignment may be required.

---

## Tool references

| Tool | upstream |
|------|----------|
| Real-ESRGAN | [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) |
| yt-dlp | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| FFmpeg | [ffmpeg.org](https://ffmpeg.org/) |

---

## License

Real-ESRGAN: BSD-3-Clause. yt-dlp: Unlicense. FFmpeg: LGPL/GPL. Repository scripts: use at your own risk for personal projects.
