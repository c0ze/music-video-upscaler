"""yt-dlp probe + scale recommendation."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict


def recommended_scale(height: int) -> int:
    """Return 2 for 1080p+, 4 for everything below (or unknown)."""
    if height >= 1080:
        return 2
    return 4


@dataclass(frozen=True)
class ProbeResult:
    title: str
    duration: float
    width: int
    height: int
    fps: float
    recommended_scale: int


class ProbeError(RuntimeError):
    """yt-dlp could not return usable metadata for the URL."""


def _resolve_ytdlp() -> str:
    found = shutil.which("yt-dlp")
    return found if found else "yt-dlp"


def parse_ytdlp_dump(payload: Dict[str, Any]) -> ProbeResult:
    try:
        title = str(payload["title"])
        duration = float(payload["duration"])
        width = int(payload["width"])
        height = int(payload["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError(f"yt-dlp payload missing required fields: {exc}") from exc

    fps_raw = payload.get("fps")
    fps = float(fps_raw) if fps_raw is not None else 0.0

    return ProbeResult(
        title=title,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        recommended_scale=recommended_scale(height),
    )


def probe(url: str, timeout: float = 30.0) -> ProbeResult:
    cmd = [_resolve_ytdlp(), "--dump-json", "--no-warnings", url]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        raise ProbeError(msg)
    text = (proc.stdout or "").strip()
    if not text:
        raise ProbeError("yt-dlp returned empty output")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(text.splitlines()[0])
        except (json.JSONDecodeError, IndexError) as exc:
            raise ProbeError(f"yt-dlp returned non-JSON output: {exc}") from exc
    return parse_ytdlp_dump(payload)
