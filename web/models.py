"""Discover Real-ESRGAN ncnn model files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

DEFAULT_MODEL = "realesr-general-x4v3"

_HINTS = {
    "realesr-general-x4v3":
        "Recommended for compressed YouTube sources (default).",
    "realesr-general-wdn-x4v3":
        "Stronger denoise; use for very noisy or heavily compressed sources.",
    "realesrgan-x4plus":
        "Sharpest output, best for genuinely clean sources.",
    "realesrgan-x4plus-anime":
        "Anime/illustration content.",
    "realesr-animevideov3":
        "Anime video, lower resource cost.",
    "realesrnet-x4plus":
        "More conservative variant of x4plus, fewer hallucinations.",
}


@dataclass(frozen=True)
class ModelInfo:
    name: str
    default: bool
    hint: str


def list_models(models_dir: Path) -> List[ModelInfo]:
    """Return all complete .param/.bin pairs in models_dir.

    Marks the default model if present. Hints attached for known names.
    Returns an empty list if the directory does not exist.
    """
    if not models_dir.is_dir():
        return []

    pairs: List[str] = []
    for param in sorted(models_dir.glob("*.param")):
        stem = param.stem
        if (models_dir / f"{stem}.bin").is_file():
            pairs.append(stem)

    return [
        ModelInfo(name=name, default=(name == DEFAULT_MODEL), hint=_HINTS.get(name, ""))
        for name in pairs
    ]
