"""FastAPI application factory and route handlers."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.jobs import JobManager
from web.models import list_models
from web.platform_info import REPO_ROOT
from web.probe import ProbeError, probe
from web.state import JobState
from web.workdir import default_output_dir

_log = logging.getLogger(__name__)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_FRAME_ID_RE = re.compile(r"^[0-9]{6}$")

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_MODELS_DIR = REPO_ROOT / "models"


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1)


def _check_health(models_dir: Path) -> dict:
    missing = []
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        if shutil.which(tool) is None:
            missing.append(tool)
    realesr_candidates = [
        REPO_ROOT / "tools" / "realesrgan-ncnn-vulkan",
        REPO_ROOT / "windows" / "realesrgan-ncnn-vulkan.exe",
    ]
    if not (
        shutil.which("realesrgan-ncnn-vulkan")
        or any(p.exists() for p in realesr_candidates)
    ):
        missing.append("realesrgan-ncnn-vulkan")
    if not list_models(models_dir):
        missing.append("models")
    return {"ok": not missing, "missing": missing}


def build_app(
    models_dir: Optional[Path] = None,
    workdir_root: Optional[Path] = None,
) -> FastAPI:
    app = FastAPI(title="music-video-upscaler", version="0.1.0")

    models_dir = (models_dir or DEFAULT_MODELS_DIR).resolve()
    job_manager = JobManager(workdir_root=workdir_root)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        index_html = STATIC_DIR / "index.html"
        if not index_html.is_file():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_html)

    @app.get("/api/health")
    def health():
        return _check_health(models_dir)

    @app.get("/api/models")
    def models():
        return [asdict(m) for m in list_models(models_dir)]

    @app.post("/api/probe")
    def probe_endpoint(req: ProbeRequest):
        try:
            result = probe(req.url)
        except ProbeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return asdict(result)

    def _spawn(coro) -> None:
        """Fire-and-forget background task with exception logging."""
        task = asyncio.create_task(coro)

        def _log_exc(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                _log.exception("background job task failed", exc_info=exc)

        task.add_done_callback(_log_exc)

    @app.post("/api/jobs")
    async def post_job(
        url: str = Form(...),
        model: str = Form(...),
        scale: int = Form(...),
        output_format: Literal["mkv", "mp4"] = Form("mkv"),
        output_dir: Optional[str] = Form(None),
        audio_file: Optional[UploadFile] = File(None),
    ):
        if scale not in (2, 4):
            raise HTTPException(status_code=422, detail="scale must be 2 or 4")
        if not _URL_RE.match(url):
            raise HTTPException(status_code=422, detail="url must start with http(s)")
        if audio_file is not None and audio_file.filename:
            if not audio_file.filename.lower().endswith(".flac"):
                raise HTTPException(status_code=422, detail="audio_file must be .flac")

        out = Path(output_dir).expanduser() if output_dir else default_output_dir()
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"output_dir not writable: {exc}")

        try:
            job_id, workdir = job_manager.register_job(
                kind="full",
                url=url,
                model=model,
                scale=scale,
                output_format=output_format,
                audio_override=None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        if audio_file is not None and audio_file.filename:
            target = workdir / "audio_override.flac"
            target.write_bytes(await audio_file.read())
            job_manager.set_audio_override(job_id, "audio_override.flac")

        _spawn(job_manager.run_full_job(job_id, output_dir=out))
        return {"job_id": job_id}

    @app.post("/api/preview")
    async def post_preview(
        url: str = Form(...),
        model: str = Form(...),
        scale: int = Form(...),
    ):
        if scale not in (2, 4):
            raise HTTPException(status_code=422, detail="scale must be 2 or 4")
        if not _URL_RE.match(url):
            raise HTTPException(status_code=422, detail="url must start with http(s)")
        try:
            job_id, _ = job_manager.register_job(
                kind="preview",
                url=url,
                model=model,
                scale=scale,
                output_format="mkv",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        _spawn(job_manager.run_preview_job(job_id))
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

        if JobState(snap["state"]).is_terminal():
            return {"already_terminal": True}

        # Best-effort: signal the running stage process if a pid was recorded.
        pid = snap.get("pid")
        if pid:
            try:
                if sys.platform == "win32":
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError) as exc:
                _log.debug("cancel signal failed for pid %s: %s", pid, exc)

        try:
            job_manager.set_state(job_id, JobState.CANCELLED)
        except Exception as exc:
            _log.debug("cancel state transition failed for %s: %s", job_id, exc)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        try:
            sub = await job_manager.subscribe(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

        async def stream():
            yield "retry: 3000\n\n"
            async for evt in sub:
                yield evt.to_sse()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/frames/{kind}/{frame_id}")
    def get_frame(job_id: str, kind: str, frame_id: str):
        if kind not in ("src", "up"):
            raise HTTPException(status_code=400, detail="kind must be src or up")
        if not _FRAME_ID_RE.match(frame_id):
            raise HTTPException(status_code=400, detail="invalid frame_id")
        try:
            workdir = job_manager.workdir.get_workdir(job_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="job not found")
        path = workdir / "thumbs" / f"{kind}_{frame_id}.jpg"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="thumbnail not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/output")
    def get_output(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        out = snap.get("output_path")
        if not out or not Path(out).is_file():
            raise HTTPException(status_code=404, detail="output not available")
        return FileResponse(out, filename=Path(out).name)

    @app.post("/api/jobs/{job_id}/reveal")
    def reveal(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        out = snap.get("output_path")
        if not out:
            raise HTTPException(status_code=404, detail="no output yet")
        target = str(Path(out).parent)
        import subprocess
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"ok": True}

    app.state.job_manager = job_manager
    app.state.models_dir = models_dir
    return app


# Lazy module-level `app` so importing this module (e.g. for tests) does not
# create the default cache/workdir on disk. `uvicorn web.server:app` still
# works because attribute lookup triggers __getattr__.
def __getattr__(name: str):
    if name == "app":
        instance = build_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
