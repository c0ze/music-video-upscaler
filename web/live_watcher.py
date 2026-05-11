"""Background watcher that emits 'thumbnail-worthy' frame ids while upscale runs."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Awaitable, Callable

FrameHandler = Callable[[str], Awaitable[None]]


async def watch_upscale_dir(
    upscale_dir: Path,
    every_n: int,
    on_frame: FrameHandler,
    stop_event: asyncio.Event,
    poll_interval: float = 1.0,
) -> None:
    """Poll upscale_dir; for each new count crossing a multiple of every_n,
    invoke on_frame with that frame's zero-padded id (e.g. '000200')."""
    last_emitted = 0
    upscale_dir.mkdir(parents=True, exist_ok=True)

    while not stop_event.is_set():
        try:
            count = sum(1 for e in os.scandir(upscale_dir) if e.is_file() and e.name.endswith(".png"))
        except FileNotFoundError:
            count = 0

        threshold = (count // every_n) * every_n
        while last_emitted + every_n <= threshold:
            last_emitted += every_n
            frame_id = f"{last_emitted:06d}"
            try:
                await on_frame(frame_id)
            except Exception:
                pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue
