"""Per-job workdir lifecycle: create, locate, clean."""
from __future__ import annotations

import json
import os
import platform as _stdlib_platform
import secrets
import shutil
import string
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def default_root() -> Path:
    if _stdlib_platform.system() == "Windows":
        cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif _stdlib_platform.system() == "Darwin":
        cache = Path.home() / "Library" / "Caches"
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache / "music-video-upscaler" / "jobs"


def default_output_dir() -> Path:
    home = Path.home()
    if _stdlib_platform.system() == "Darwin":
        return home / "Movies" / "MusicVideoUpscaled"
    if _stdlib_platform.system() == "Windows":
        return home / "Videos" / "MusicVideoUpscaled"
    return home / "Videos" / "MusicVideoUpscaled"


_TERMINAL = {"complete", "failed", "cancelled"}
_ALPHABET = string.ascii_lowercase + string.digits


def _new_job_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"{ts}-{suffix}"


class WorkdirManager:
    def __init__(
        self,
        root: Optional[Path] = None,
        keep_recent: int = 5,
        max_age_seconds: float = 7 * 24 * 3600,
    ) -> None:
        self.root = (root or default_root()).resolve()
        self.keep_recent = keep_recent
        self.max_age_seconds = max_age_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job(self) -> Tuple[str, Path]:
        for _ in range(8):
            job_id = _new_job_id()
            workdir = self.root / job_id
            try:
                workdir.mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                time.sleep(0.01)
                continue
        else:
            raise RuntimeError("could not allocate a fresh job id")
        for sub in ("source", "thumbs", "output"):
            (workdir / sub).mkdir(parents=True, exist_ok=True)
        return job_id, workdir

    def get_workdir(self, job_id: str) -> Path:
        wd = self.root / job_id
        if not wd.is_dir():
            raise FileNotFoundError(f"workdir not found: {job_id}")
        return wd

    def state_path(self, job_id: str) -> Path:
        return self.get_workdir(job_id) / "state.json"

    def log_path(self, job_id: str) -> Path:
        return self.get_workdir(job_id) / "log.txt"

    def cleanup(self) -> None:
        now = time.time()
        candidates = [p for p in self.root.iterdir() if p.is_dir()]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        recent = set(candidates[: self.keep_recent])
        for wd in candidates:
            if wd in recent:
                continue
            age = now - wd.stat().st_mtime
            if age <= self.max_age_seconds:
                continue
            state = "unknown"
            sp = wd / "state.json"
            if sp.is_file():
                try:
                    state = json.loads(sp.read_text()).get("state", "unknown")
                except (json.JSONDecodeError, OSError):
                    state = "unknown"
            if state not in _TERMINAL and state != "unknown":
                continue
            try:
                shutil.rmtree(wd)
            except OSError:
                pass
