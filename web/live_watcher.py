"""Background watcher that emits 'thumbnail-worthy' frame ids while upscale runs."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable

FrameHandler = Callable[[str], Awaitable[None]]

_log = logging.getLogger(__name__)


async def watch_upscale_dir(
    upscale_dir: Path,
    every_n: int,
    on_frame: FrameHandler,
    stop_event: asyncio.Event,
    poll_interval: float = 1.0,
) -> None:
    """Poll upscale_dir; for each new count crossing a multiple of every_n,
    invoke on_frame with that frame's zero-padded id (e.g. '000200')."""
    if every_n <= 0:
        raise ValueError(f"every_n must be positive, got {every_n}")

    last_emitted = 0
    upscale_dir.mkdir(parents=True, exist_ok=True)

    while not stop_event.is_set():
        try:
            count = sum(1 for e in os.scandir(upscale_dir) if e.is_file() and e.name.endswith(".png"))
        except FileNotFoundError:
            count = 0

        threshold = (count // every_n) * every_n
        while last_emitted + every_n <= threshold:
            if stop_event.is_set():
                break
            last_emitted += every_n
            frame_id = f"{last_emitted:06d}"
            try:
                await on_frame(frame_id)
            except Exception:
                _log.exception("on_frame callback raised for %s; continuing watch", frame_id)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue
