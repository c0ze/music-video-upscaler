"""OS detection + stage-script path resolution.

Module is named ``platform_info`` to avoid shadowing the stdlib ``platform``.
"""
from __future__ import annotations

import platform as _stdlib_platform
from pathlib import Path
from typing import Dict, List

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


def is_windows() -> bool:
    return _stdlib_platform.system() == "Windows"


_STAGE_SCRIPTS_POSIX: Dict[str, Path] = {
    "sanitize":   REPO_ROOT / "00_sanitize.sh",
    "sync_audio": REPO_ROOT / "01_sync_audio.sh",
    "extract":    REPO_ROOT / "02_extract.sh",
    "upscale":    REPO_ROOT / "03_upscale.sh",
    "mux":        REPO_ROOT / "04_mux.sh",
}

_STAGE_SCRIPTS_WINDOWS: Dict[str, Path] = {
    "sanitize":   REPO_ROOT / "windows" / "00_sanitize.ps1",
    "sync_audio": REPO_ROOT / "windows" / "01_sync_audio.ps1",
    "extract":    REPO_ROOT / "windows" / "02_extract.ps1",
    "upscale":    REPO_ROOT / "windows" / "03_upscale.ps1",
    "mux":        REPO_ROOT / "windows" / "04_mux.ps1",
}


def stage_script(stage: str) -> Path:
    table = _STAGE_SCRIPTS_WINDOWS if is_windows() else _STAGE_SCRIPTS_POSIX
    return table[stage]


def stage_command(stage: str, args: List[str]) -> List[str]:
    script = stage_script(stage)
    if is_windows():
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            *args,
        ]
    return [str(script), *args]
