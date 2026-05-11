"""360px thumbnail generation: Pillow primary, ffmpeg fallback."""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False


@dataclass
class ThumbnailGenerator:
    prefer_pillow: bool = True
    quality: int = 80

    async def generate(self, src: Path, dst: Path, width: int = 360) -> None:
        if dst.is_file() and dst.stat().st_size > 0:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if self.prefer_pillow and _HAS_PILLOW:
            await asyncio.to_thread(self._generate_pillow, src, dst, width)
        else:
            await self._generate_ffmpeg(src, dst, width)

    def _generate_pillow(self, src: Path, dst: Path, width: int) -> None:
        with Image.open(src) as im:
            im = im.convert("RGB")
            ratio = width / im.size[0]
            new_size = (width, max(1, int(round(im.size[1] * ratio))))
            im = im.resize(new_size, Image.LANCZOS)
            im.save(dst, "JPEG", quality=self.quality, optimize=True)

    async def _generate_ffmpeg(self, src: Path, dst: Path, width: int) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner", "-nostdin", "-y",
            "-i", str(src),
            "-vf", f"scale={width}:-1",
            "-q:v", "5",
            str(dst),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0 or not dst.is_file():
            raise RuntimeError(f"ffmpeg thumbnail generation failed for {src}")
