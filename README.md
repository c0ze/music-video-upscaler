# Music Video Upscaler

AI-powered video upscaling pipeline for creating high-quality music videos with lossless audio.

This project takes YouTube music videos, upscales them to 2K or 4K using Real-ESRGAN, and muxes them with lossless FLAC audio from CD rips for archival-quality releases.

---

## Features

- **AI Upscaling**: Uses Real-ESRGAN (NCNN/Vulkan) for high-quality 2x or 4x upscaling
- **Lossless Audio**: Replaces compressed YouTube audio with FLAC from CD/studio sources
- **Automatic Audio Sync**: Detects silence and aligns FLAC audio to video timing
- **Batch Processing**: Automated pipeline from download to final release
- **GPU Accelerated**: Vulkan-based upscaling works on NVIDIA, AMD, and Intel GPUs

---

## Requirements

### Included in Repository

These tools are bundled in the repo and ready to use:

| Tool | Description |
|------|-------------|
| `realesrgan-ncnn-vulkan.exe` | AI upscaler (Vulkan GPU acceleration) |
| `yt-dlp.exe` | YouTube video/audio downloader |
| `vcomp140.dll` / `vcomp140d.dll` | OpenMP runtime (required by Real-ESRGAN) |
| `models/` | Pre-trained upscaling models |

### Must Be Installed

These tools must be installed and available in your system PATH:

| Tool | Description | Installation |
|------|-------------|--------------|
| **FFmpeg** | Video processing (frame extraction, muxing) | See below |
| **FFprobe** | Video analysis (framerate, duration) | Bundled with FFmpeg |
| **PowerShell 5.1+** | Script execution (pre-installed on Windows 10/11) | - |

---

## Installation

### 1. Clone or Download This Repository

```powershell
git clone https://github.com/yourusername/music-video-upscaler.git
cd music-video-upscaler
```

### 2. Install FFmpeg

FFmpeg and FFprobe are required for all video processing operations.

**Option A: Using winget (Recommended)**
```powershell
winget install Gyan.FFmpeg
```

**Option B: Using Chocolatey**
```powershell
choco install ffmpeg
```

**Option C: Manual Installation**
1. Download from: https://www.gyan.dev/ffmpeg/builds/
   - Choose `ffmpeg-release-essentials.zip` for most users
2. Extract to a folder (e.g., `C:\ffmpeg`)
3. Add to PATH:
   - Open System Properties → Advanced → Environment Variables
   - Edit `Path` under User variables
   - Add `C:\ffmpeg\bin`
4. Restart your terminal

**Verify Installation:**
```powershell
ffmpeg -version
ffprobe -version
```

### 3. Verify GPU Support

Real-ESRGAN uses Vulkan for GPU acceleration. Most modern GPUs (NVIDIA, AMD, Intel) support Vulkan out of the box.

```powershell
# Test Real-ESRGAN
.\realesrgan-ncnn-vulkan.exe -h
```

---

## Usage

### Quick Start: Full Pipeline

Run the complete pipeline on a folder containing a video and FLAC audio:

```powershell
.\run_pipeline.ps1 -TargetFolder .\artist_folder -YouTubeUrl "https://www.youtube.com/watch?v=..." -Scale 4
```

The pipeline will:
1. Sanitize filenames (lowercase, remove special characters)
2. Sync audio timing (add silence to FLAC if needed)
3. Extract frames from video
4. Upscale each frame with Real-ESRGAN
5. Mux frames + FLAC audio into final MKV

### Manual Workflow

#### Step 1: Prepare Your Files

Create a folder for each video with:
- The source video (`.mp4`, `.webm`, or `.mkv`)
- The lossless audio file (`.flac` or `.wav`)

```
artist/
├── song_title.mp4      # Downloaded from YouTube
└── song_title.flac     # From CD rip
```

#### Step 2: Sanitize Filenames (Optional)

```powershell
.\00_sanitize.ps1 -Directory .\artist
```

#### Step 3: Sync Audio

```powershell
.\01_sync_audio.ps1 -InputVideo .\artist\song.mp4 -InputAudio .\artist\song.flac -YouTubeUrl "https://..."
```

#### Step 4: Extract Frames

```powershell
.\02_extract.ps1 -InputVideo .\artist\song.mp4 -OutputFramesDir .\artist\tmp_frames
```

#### Step 5: Upscale Frames

```powershell
.\03_upscale.ps1 -InputFramesDir .\artist\tmp_frames -OutputUpscaledDir .\artist\tmp_upscaled_4x -Scale 4 -Model realesrgan-x4plus
```

#### Step 6: Mux Final Video

```powershell
.\04_mux.ps1 -FramesDir .\artist\tmp_upscaled_4x -AudioPath .\artist\song_synced.flac -OriginalVideo .\artist\song.mp4 -OutputVideo .\output\ARTIST\song_HQ.mkv
```

### Advanced: Standalone Upscale Script

For more control, use the full-featured standalone script:

```powershell
.\upscale_video.ps1 `
    -InputVideo ".\artist\video.mp4" `
    -InputAudio ".\artist\audio.flac" `
    -Scale 4 `
    -Model "realesrgan-x4plus" `
    -YouTubeUrl "https://..." `
    -OutputFormat mkv
```

**Parameters:**
- `-Scale`: 2 or 4 (default: 4)
- `-Model`: `realesrgan-x4plus`, `realesr-animevideov3`, `realesrgan-x4plus-anime`
- `-OutputFormat`: `mkv` (FLAC audio) or `mp4` (AAC audio)
- `-SkipExtract`: Skip frame extraction if frames exist
- `-SkipUpscale`: Skip upscaling if upscaled frames exist
- `-SkipAudioSync`: Skip audio sync detection

### Monitor Upscale Progress

For long-running upscales, monitor progress in a separate terminal:

```powershell
.\monitor_progress.ps1 -TargetFrames 8000 -Directory ".\artist\tmp_upscaled_4x"
```

---

## Upscaling Guidelines

| Source Resolution | Scale Factor | Recommended Model | Final Resolution |
|-------------------|--------------|-------------------|------------------|
| 480p or lower | 4x | `realesrgan-x4plus` | ~1920x1080+ |
| 720p | 4x | `realesrgan-x4plus` | ~2880x1620 |
| 1080p | 2x | `realesr-animevideov3` | 3840×2160 (4K) |

> **Note:** Final video should never exceed 4K (3840×2160).

### Available Models

| Model | Best For | Scale Options |
|-------|----------|---------------|
| `realesrgan-x4plus` | General real-world content | 4x only |
| `realesr-animevideov3` | Anime/animation, video content | 2x, 3x, 4x |
| `realesrgan-x4plus-anime` | Anime with 4x upscale | 4x only |

---

## Project Structure

```
music-video-upscaler/
├── .gemini/                    # AI assistant context
├── models/                     # Real-ESRGAN model files
│   ├── realesrgan-x4plus.bin/.param
│   ├── realesr-animevideov3-x2.bin/.param
│   ├── realesr-animevideov3-x3.bin/.param
│   ├── realesr-animevideov3-x4.bin/.param
│   └── realesrgan-x4plus-anime.bin/.param
├── METAL_VIDS_UPSCALED_FLAC/   # Final release output
│   └── ARTIST/                 # Organized by artist
│       ├── song_HQ.mkv         # Final video
│       └── song_HQ.txt         # Release notes
├── 00_sanitize.ps1             # Filename normalization
├── 01_sync_audio.ps1           # Audio timing sync
├── 02_extract.ps1              # Frame extraction
├── 03_upscale.ps1              # AI upscaling
├── 04_mux.ps1                  # Final video assembly
├── run_pipeline.ps1            # Automated full pipeline
├── upscale_video.ps1           # Standalone full-featured script
├── monitor_progress.ps1        # Upscale progress monitor
├── realesrgan-ncnn-vulkan.exe  # AI upscaler binary
├── yt-dlp.exe                  # YouTube downloader
├── vcomp140.dll                # OpenMP runtime
├── vcomp140d.dll               # OpenMP runtime (debug)
└── README.md                   # This file
```

---

## Output Format

Final releases are saved to `METAL_VIDS_UPSCALED_FLAC/{ARTIST}/`:

- **Container**: Matroska (MKV)
- **Video Codec**: H.264/AVC at CRF 18 (high quality)
- **Audio Codec**: FLAC (losslessly copied from source)

---

## Troubleshooting

### "ffmpeg is not recognized"
FFmpeg is not in your PATH. Follow the installation instructions above.

### Real-ESRGAN fails to start
- Ensure `vcomp140.dll` and `vcomp140d.dll` are in the same folder as `realesrgan-ncnn-vulkan.exe`
- Check that your GPU drivers are up to date
- Try running with `-v` flag for verbose output

### GPU not detected
- Update your graphics drivers
- Ensure Vulkan support is installed (usually included with GPU drivers)
- Try specifying GPU ID: `.\realesrgan-ncnn-vulkan.exe -g 0`

### Audio sync issues
- Duration mismatch warning: The video may have cuts/edits not in the album version
- Try manually adjusting with an audio editor or re-syncing with different parameters

---

## Tool Sources & References

| Tool | Source | Documentation |
|------|--------|---------------|
| **Real-ESRGAN** | https://github.com/xinntao/Real-ESRGAN | [Paper](https://arxiv.org/abs/2107.10833) |
| **NCNN** | https://github.com/Tencent/ncnn | Inference framework |
| **yt-dlp** | https://github.com/yt-dlp/yt-dlp | YouTube downloader |
| **FFmpeg** | https://ffmpeg.org/ | [Download](https://www.gyan.dev/ffmpeg/builds/) |

---

## License

This project uses the following open-source tools:
- Real-ESRGAN: BSD-3-Clause License
- yt-dlp: Unlicense
- FFmpeg: LGPL/GPL

The scripts in this repository are provided as-is for personal use.
