# Web UI

Thin local web UI for the music-video upscaling pipeline. Paste a YouTube URL,
pick a model and scale, optionally upload a FLAC, preview a few sample frames,
and watch the full upscale stream live.

## Install

```bash
./install-dependencies.sh --with-web
```

(or `windows\install-dependencies.ps1 -WithWeb`)

This creates `web/.venv` and installs the FastAPI/uvicorn dependencies into it
on top of the normal pipeline tools (ffmpeg, ffprobe, yt-dlp,
realesrgan-ncnn-vulkan).

## Run

```bash
./web/run_server.sh         # macOS/Linux
web\run_server.ps1          # Windows
```

Open `http://127.0.0.1:8765/`.

## Override host/port

```bash
HOST=0.0.0.0 PORT=9000 ./web/run_server.sh
```

> **Note:** binding to `0.0.0.0` exposes the server to your LAN. There is no
> authentication. Only do this on trusted networks.

## What it actually does

The server is a thin shell over the existing pipeline scripts
(`00_sanitize.sh`…`04_mux.sh` on POSIX, `windows\*.ps1` on Windows). It runs
each stage as its own subprocess, streams stdout into the browser via
Server-Sent Events, and serves a few thumbnails so you can see results.

Job artifacts are stored under
`~/.cache/music-video-upscaler/jobs/<job_id>/` (XDG-respecting on Linux,
`~/Library/Caches/...` on macOS, `%LOCALAPPDATA%\...` on Windows). The final
muxed file is copied into your output folder (default
`~/Movies/MusicVideoUpscaled/` on macOS, `~/Videos/MusicVideoUpscaled/`
elsewhere; override per-job via the `output_dir` form field on `POST /api/jobs`).

On startup the server prunes terminal job workdirs older than 7 days, while
keeping the 5 most recent and any non-terminal jobs.

## Tests

```bash
web/.venv/bin/pytest web/tests
```

The integration smoke test (`test_pipeline_smoke.py`) is skipped automatically
when ffmpeg, ffprobe, realesrgan-ncnn-vulkan, or the default model are missing.

A manual end-to-end smoke checklist lives at `web/tests/manual_smoke.md`.

## Design

See `docs/superpowers/specs/2026-05-11-web-frontend-design.md`.
