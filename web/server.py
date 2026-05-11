"""FastAPI application factory and route handlers."""
from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.jobs import JobManager
from web.models import list_models
from web.platform_info import REPO_ROOT
from web.probe import ProbeError, probe

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
