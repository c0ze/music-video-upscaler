import asyncio
from pathlib import Path

import pytest

from web.live_watcher import watch_upscale_dir


@pytest.mark.asyncio
async def test_watcher_emits_every_n_frames(tmp_path):
    seen = []

    async def on_frame(frame_id: str) -> None:
        seen.append(frame_id)

    stop = asyncio.Event()

    async def producer():
        for i in range(1, 11):
            (tmp_path / f"{i:06d}.png").write_bytes(b"x")
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        stop.set()

    watcher = asyncio.create_task(
        watch_upscale_dir(tmp_path, every_n=4, on_frame=on_frame, stop_event=stop, poll_interval=0.05)
    )
    await producer()
    await watcher

    # crossed 4 (000004) and 8 (000008)
    assert "000004" in seen
    assert "000008" in seen
    assert "000010" not in seen


@pytest.mark.asyncio
async def test_watcher_stops_on_event(tmp_path):
    stop = asyncio.Event()
    stop.set()
    seen = []

    async def on_frame(_: str) -> None:
        seen.append(_)

    await asyncio.wait_for(
        watch_upscale_dir(tmp_path, every_n=1, on_frame=on_frame, stop_event=stop, poll_interval=0.01),
        timeout=1.0,
    )
    assert seen == []


@pytest.mark.asyncio
async def test_watcher_rejects_non_positive_every_n(tmp_path):
    stop = asyncio.Event()

    async def on_frame(_: str) -> None:
        pass

    with pytest.raises(ValueError):
        await watch_upscale_dir(tmp_path, every_n=0, on_frame=on_frame, stop_event=stop)


@pytest.mark.asyncio
async def test_watcher_swallows_and_logs_on_frame_exceptions(tmp_path, caplog):
    import logging

    seen = []

    async def on_frame(frame_id: str) -> None:
        seen.append(frame_id)
        raise RuntimeError(f"boom for {frame_id}")

    stop = asyncio.Event()

    async def producer():
        for i in range(1, 9):
            (tmp_path / f"{i:06d}.png").write_bytes(b"x")
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)
        stop.set()

    with caplog.at_level(logging.ERROR, logger="web.live_watcher"):
        watcher = asyncio.create_task(
            watch_upscale_dir(tmp_path, every_n=4, on_frame=on_frame, stop_event=stop, poll_interval=0.02)
        )
        await producer()
        await watcher

    assert "000004" in seen
    assert any("on_frame callback raised" in rec.message for rec in caplog.records)
