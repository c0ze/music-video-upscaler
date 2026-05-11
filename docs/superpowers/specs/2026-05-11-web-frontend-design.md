# Web Frontend — Design Spec

- **Date**: 2026-05-11
- **Status**: Approved (pending implementation plan)
- **Scope**: Add a thin local web UI to drive the existing upscaling pipeline. Paste a YouTube URL, pick model and scale, optionally attach a FLAC, preview a few sample frames, run the full pipeline, watch progress with live thumbnails, retrieve the result.
- **Out of scope** (deliberate, see "Non-goals"): in-browser GPU compute, multi-user, auth, persistent history, mobile polish.

## Goals

1. Give the existing CLI pipeline a usable single-page UI without modifying any of the existing pipeline scripts.
2. Run on the same machine that holds the GPU / Apple Silicon / source files. No remote execution.
3. Be cheap to install and reversible — drop one new directory (`web/`), one optional flag in the existing installers, no changes to any current entry point.
4. Expose the parts of the pipeline that benefit from interactivity: model choice, preview, live progress, cancel.
5. Match the cross-platform parity of the rest of the repo (macOS, Linux, Windows).

## Non-goals

- Multi-user / multi-job queueing. One job at a time, globally.
- Authentication, TLS, remote access. Localhost only. Server documents that exposing it is unsafe.
- WebGPU / in-browser upscaling. The user's hardware lives on the host; the browser is just a control surface.
- Persistent job history UI. Old workdirs are kept for 7 days for inspection but there is no listing UI.
- Re-running a completed job from a "rerun with different model" button. The user can just submit a new job.
- Mobile layout polish. Tablet should work; phone is not a target.

## Approach

**Python (FastAPI + uvicorn) backend, vanilla HTML/JS frontend, Server-Sent Events for progress.** Subprocess the existing per-stage scripts.

Rationale: yt-dlp is already a Python tool; FastAPI gives async + SSE out of the box; vanilla JS avoids a build pipeline; SSE matches the natural shape of "stream log lines + thumbnail URLs as they happen." Alternatives considered: Node/Express (introduces a runtime nothing else uses), Go single-binary (highest implementation cost, hardest to hack on).

## Architecture

### Process model

- One Python process per machine. Started via `web/run_server.sh` (mac/linux) or `web/run_server.ps1` (windows).
- Listens on `127.0.0.1:8765` by default. `HOST` and `PORT` env vars override.
- Single global "current job" slot. Concurrent submissions return `409 Conflict` with the active `job_id`.
- The server **calls each numbered stage script as its own subprocess** (`00_sanitize` → yt-dlp download (new) → `01_sync_audio` → `02_extract` → `03_upscale` → `04_mux`). The existing top-level wrappers (`run_pipeline.sh`, `windows\run_pipeline.ps1`) are **not** used by the server — calling stages directly is what gives per-stage progress without modifying the bash.
- The yt-dlp download is a **new stage owned by the server** ("downloading"). The current pipeline assumes the source is already on disk; the server adds this step in front.
- Cross-platform dispatch: server detects host OS and runs `*.sh` (mac/linux) or `windows\*.ps1` (windows). Existing scripts are unchanged.

### Layout in repo

```
web/
  server.py                    # FastAPI app, route handlers
  jobs.py                      # JobManager: state machine, workdir, subprocess control
  thumbnails.py                # Pillow + ffmpeg fallback
  probe.py                     # yt-dlp --dump-json wrapper
  models.py                    # scan models/ for available .param/.bin pairs
  platform.py                  # OS detection + per-OS script paths
  static/
    index.html
    app.js
    style.css
  tests/
    fixtures/tiny.mkv
    test_states.py
    test_workdir.py
    test_probe.py
    test_recommend.py
    test_events.py
    test_pipeline_smoke.py     # skipped if deps missing
    manual_smoke.md
  requirements.txt
  run_server.sh
  run_server.ps1
  README.md
```

### Workdir

Per-job workdir under `~/.cache/music-video-upscaler/jobs/<job_id>/`. `job_id` format: `YYYYMMDD-HHMMSS-<6-char-random>`.

```
<job_id>/
  state.json
  log.txt
  source/
    video.<ext>
    audio.<ext>
  audio_override.flac        (only if user uploaded one)
  tmp_frames/
  tmp_upscaled_<N>x/
  thumbs/
    src_000123.jpg
    up_000123.jpg
  output/
    <basename>_realesrgan_<model>_<N>x_HQ.<fmt>
```

The final output is symlinked into the user's chosen output folder. Default destinations:

| OS      | Default output dir                                  |
|---------|-----------------------------------------------------|
| macOS   | `~/Movies/MusicVideoUpscaled/`                      |
| Linux   | `~/Videos/MusicVideoUpscaled/`                      |
| Windows | `%USERPROFILE%\Videos\MusicVideoUpscaled\`          |

Cleanup at server start: prune workdirs older than 7 days, except (a) the most recent 5, (b) any whose state is non-terminal.

### `state.json` shape

```json
{
  "job_id": "20260511-085732-a3f9k2",
  "kind": "full",
  "state": "upscaling",
  "url": "https://www.youtube.com/watch?v=...",
  "model": "realesr-general-x4v3",
  "scale": 4,
  "output_format": "mkv",
  "audio_override": "audio_override.flac",
  "started_at": "2026-05-11T08:57:32+09:00",
  "stage_progress": {
    "extract": {"current": 4500, "total": 4500},
    "upscale": {"current": 1024, "total": 4500}
  },
  "output_path": null,
  "error": null,
  "pid": 23456
}
```

`kind ∈ {full, preview}`. `state ∈ {created, downloading, preparing, extracting, upscaling, muxing, complete, failed, cancelled}`.

### Stage → state mapping

The server runs more sub-steps than the UI shows, so internal states aggregate them:

| Internal state | Sub-steps run by the server                          | UI label    |
|----------------|------------------------------------------------------|-------------|
| `downloading`  | `yt-dlp` source download                             | Downloading |
| `preparing`    | `00_sanitize.sh` + `01_sync_audio.sh`                | Sync        |
| `extracting`   | `02_extract.sh`                                      | Extract     |
| `upscaling`    | `03_upscale.sh`                                      | Upscale     |
| `muxing`       | `04_mux.sh`                                          | Mux         |

## HTTP API

| Method | Path                                            | Purpose |
|--------|-------------------------------------------------|---------|
| `GET`  | `/`                                             | `index.html` |
| `GET`  | `/static/*`                                     | JS, CSS, icons |
| `GET`  | `/api/health`                                   | `{ok, missing: ["realesrgan-ncnn-vulkan", ...]}` |
| `GET`  | `/api/models`                                   | `[{name, default, hint}]` from scanning `models/` |
| `POST` | `/api/probe`                                    | Body: `{url}`. Runs `yt-dlp --dump-json` (no download, no workdir created). Returns `{title, duration, width, height, fps, recommended_scale}`. |
| `POST` | `/api/preview`                                  | Multipart: `{url, model, scale}`. Returns `{job_id}`. Downloads only the first 10s, extracts 5 frames, upscales them. |
| `POST` | `/api/jobs`                                     | Multipart: `{url, model, scale, output_format, output_dir?, audio_file?}`. Returns `{job_id}`. `audio_file` must be `.flac` and pass an `ffprobe` sanity check; `output_dir` must be writable. Validation failures → `400` with field-level errors. |
| `GET`  | `/api/jobs/{id}`                                | Snapshot of `state.json`. |
| `GET`  | `/api/jobs/{id}/events`                         | SSE stream. Closes on terminal state. |
| `POST` | `/api/jobs/{id}/cancel`                         | SIGTERM proc group → 10s grace → SIGKILL. |
| `GET`  | `/api/jobs/{id}/frames/{kind}/{frame_id}`       | 360px JPEG thumbnail. `kind ∈ {src, up}`. Cached on disk. |
| `GET`  | `/api/jobs/{id}/output`                         | Downloads the final muxed file. |
| `POST` | `/api/jobs/{id}/reveal`                         | Opens output folder via `open` / `xdg-open` / `explorer`. |

### SSE event schema

```json
{"type": "stage",     "stage": "upscale", "status": "started"}
{"type": "stage",     "stage": "extract", "status": "done", "extra": {"frame_count": 4500}}
{"type": "progress",  "stage": "upscale", "current": 1024, "total": 4500}
{"type": "thumbnail", "frame_id": "000123", "kind": "up", "url": "/api/jobs/abc/frames/up/000123"}
{"type": "log",       "line": "..."}
{"type": "complete",  "output": "/path/to/file.mkv", "size_bytes": 123456789}
{"type": "error",     "stage": "upscale", "message": "..."}
```

## UI / UX flow

Single-page app, top-down vertical. Plain HTML + one `app.js` (~300 lines), no framework, no build step. ~150 lines of CSS, dark theme. Five panels stacked; later panels disabled until earlier ones complete.

### Panel 1 — Source
- Text input: YouTube URL.
- Button: **Probe**. Disabled until URL pattern is plausible (`/^https?:\/\/(www\.)?(youtube\.com|youtu\.be)\//`).
- After probe success: read-only summary line — `"Title — 04:12 — 854x480 @ 23.976 fps"`.
- On probe failure: red inline message with the yt-dlp error verbatim.

### Panel 2 — Settings (enabled after probe)
- **Model** dropdown — populated from `/api/models`. Default: `realesr-general-x4v3`. Each option shows a one-line hint.
- **Scale** dropdown — `2x`, `4x`. Pre-selected by `recommended_scale` (height ≥ 1080 → 2x, else 4x). User can override.
- **Output format** — `mkv`, `mp4`. Default `mkv`.
- **Output folder** — text input, pre-filled with the OS default. (Optional.)
- **Optional FLAC override** — file input + drag-drop. If empty, audio comes from yt-dlp.
- Two action buttons:
  - **Preview** (secondary) — runs the cheap 5-frame preview job.
  - **Run** (primary) — runs the full pipeline.

### Panel 3 — Preview results (visible only after a preview job)
- Grid of 5 frames. Each cell: a hover/slider swap between original and upscaled JPEG (full-size linked, 360px thumbs displayed).
- Caption: model + scale used.
- Hides when the user changes model or scale (forces re-preview).

### Panel 4 — Job progress (visible during full run)
- Stage indicator: `Downloading → Sync → Extract → Upscale → Mux → Complete`. Current stage highlighted.
- Progress bar with text: `"Upscaling 1240 / 4500 frames (28%)"`. Computed by counting files in `tmp_upscaled_<N>x/` vs known frame total from extract stage.
- Live thumbnail strip: every Nth upscaled frame (default N=200) appears as a small thumbnail (max 12 visible, oldest scrolls off).
- Collapsible log (`<details>`).
- **Cancel** button.

### Panel 5 — Done
- Output path + file size + total run duration.
- Buttons: **Download**, **Reveal in file manager**, **New job** (resets the form).
- On failure: red banner with `error` message + last 50 log lines.

### UX details
- `job_id` of any running job stored in `localStorage`. On page load, server is queried for that job's state; if still active, the events stream is reattached and the UI jumps straight to Panel 4.
- All buttons disabled when `state ∈ {downloading, preparing, extracting, upscaling, muxing}` except Cancel.
- No styling framework.

## Thumbnails

- Always 360px-wide JPEG, quality 80.
- Generated by Pillow when available; `ffmpeg -vf scale=360:-1` fallback when not.
- Source thumbnails generated on demand (preview, or when the live strip needs an "original next to me" comparison — v1 only emits upscaled live thumbnails).
- Live strip during upscale: a Python `asyncio` task `os.scandir`s `tmp_upscaled_<N>x/` every 1s while the `upscaling` state is active. Each time the count crosses a multiple of N (default 200), it picks that frame, generates a thumbnail, emits a `thumbnail` SSE event. Task is cancelled when the state leaves `upscaling`.
- Cached on disk in `<workdir>/thumbs/`.

## Error handling

- **Startup health check** (`/api/health`): tests `ffmpeg`, `ffprobe`, `yt-dlp`, `realesrgan-ncnn-vulkan`, and that at least one `.param`/`.bin` pair exists in `models/`. UI shows a red banner if anything is missing, with the install command for the host OS.
- **Subprocess failures**: capture exit code + last 50 lines, write into `state.json.error`, transition to `failed`, send `error` SSE, close the stream.
- **Cancellation**: server keeps `pid` of the active stage subprocess. Cancel handler sends SIGTERM to the process group (POSIX) or `taskkill /T` (Windows), waits 10s, then SIGKILL / `taskkill /F`. Workdir is left in place. State → `cancelled`.
- **yt-dlp failures** (private video, geo-block, dead URL, age-gated): bubbled verbatim into the `error` field. UI surfaces them in red.
- **Disk-full / permission errors**: caught at stage subprocess level, surfaced the same way.
- **Browser disconnect during long run**: job continues. Reconnect via the stored `job_id` in localStorage replays state (`GET /api/jobs/<id>` for snapshot, then `GET /api/jobs/<id>/events` for the rest).
- **Missing model**: gated client-side by what `/api/models` returned. Server re-validates on POST.

## Dependencies

`web/requirements.txt`:
```
fastapi
uvicorn[standard]
python-multipart
pillow
```

Launchers:
- `web/run_server.sh` (mac/linux): creates `.venv` if missing, `pip install -r requirements.txt`, then `uvicorn web.server:app --host 127.0.0.1 --port 8765`.
- `web/run_server.ps1` (windows): same with `python -m venv` + `pip`.

`install-dependencies.sh` and `windows/install-dependencies.ps1` get a new optional flag `--with-web` (or `-WithWeb` on Windows) that also creates the venv and installs `requirements.txt`. Without the flag, the existing CLI flow is unaffected.

## Testing

### Backend unit tests (pytest, `web/tests/test_*.py`)

- `test_states.py` — state machine transitions, illegal transitions raise.
- `test_workdir.py` — workdir paths resolved correctly per OS, cleanup keeps the right ones.
- `test_probe.py` — fixture `yt-dlp --dump-json` blobs parse into `ProbeResult`. Edge cases: missing fps, missing height, age-gated error response.
- `test_recommend.py` — `recommended_scale(height)` returns `2` for ≥1080, `4` otherwise.
- `test_events.py` — SSE event serialisation round-trips correctly, terminal events close the stream.
- `test_models.py` — scanning `models/` returns the right defaults / hints.

### Backend integration test

- `test_pipeline_smoke.py` — bundled tiny 2-second synthetic video in `web/tests/fixtures/tiny.mkv`. Runs the full pipeline. Asserts output exists and is non-zero. Skipped automatically when `realesrgan-ncnn-vulkan`, `ffmpeg`, or a default model file is missing.

### Manual smoke

- `web/tests/manual_smoke.md` — checklist for a real YouTube URL: probe, preview, live thumbnails, cancel, reattach after refresh, completion, download, reveal.

### No frontend test harness

The JS is small and stateless enough that visual smoke is sufficient for v1. If the JS grows past ~500 lines or starts holding meaningful state, revisit.

## Open questions

None at design time. Choices that may change with usage:

- **Thumbnail interval N=200** — may be tuned per typical video length once we use it.
- **Default port 8765** — arbitrary; change if it collides.
- **Workdir under `~/.cache/`** — could move to `~/Library/Caches/` on macOS for purity. Cache dir is XDG-respecting; macOS Caches still works fine.
