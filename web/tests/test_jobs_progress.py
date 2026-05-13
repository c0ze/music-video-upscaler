import asyncio

import pytest

from web.events import ProgressEvent
from web.jobs import JobManager, _thumbnail_stride, watch_upscale_progress


class _FakeDirEntry:
    def __init__(self, name: str) -> None:
        self.name = name

    def is_file(self) -> bool:
        return True


def _fake_png_entries(count: int):
    return [_FakeDirEntry(f"{index:06d}.png") for index in range(count)]


def _register_job(tmp_path):
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full",
        url="u",
        model="m",
        scale=4,
        output_format="mkv",
    )
    return mgr, job_id


async def _collect_progress(mgr: JobManager, job_id: str, coro):
    events = []
    sub = await mgr.subscribe(job_id)

    async def collect():
        async for event in sub:
            if isinstance(event, ProgressEvent):
                events.append(event)

    collector = asyncio.create_task(collect())
    await coro
    await mgr.close_subscribers(job_id)
    await collector
    return events


def test_thumbnail_stride_scales_down_thumbnail_frequency():
    assert _thumbnail_stride(frame_count=120) == 200
    assert _thumbnail_stride(frame_count=1600) == 200
    assert _thumbnail_stride(frame_count=4800) == 600


@pytest.mark.asyncio
async def test_watch_upscale_progress_emits_when_count_advances(tmp_path):
    mgr, job_id = _register_job(tmp_path)
    upscaled_dir = tmp_path / "upscaled"
    upscaled_dir.mkdir()
    stop = asyncio.Event()

    async def producer():
        await asyncio.sleep(0.03)
        (upscaled_dir / "000001.png").write_bytes(b"x")
        await asyncio.sleep(0.03)
        (upscaled_dir / "000002.png").write_bytes(b"x")
        await asyncio.sleep(0.03)
        stop.set()

    events = await _collect_progress(
        mgr,
        job_id,
        asyncio.gather(
            producer(),
            watch_upscale_progress(
                mgr,
                job_id,
                upscaled_dir,
                frame_count=4,
                stop_event=stop,
                poll_interval=0.01,
            ),
        )
    )

    assert [
        (event.stage, event.current, event.total) for event in events
    ] == [("upscaling", 1, 4), ("upscaling", 2, 4)]


@pytest.mark.asyncio
async def test_watch_upscale_progress_does_not_duplicate_same_count(tmp_path, monkeypatch):
    mgr, job_id = _register_job(tmp_path)
    stop = asyncio.Event()
    scan_count = 0

    def fake_scandir(_path):
        nonlocal scan_count
        scan_count += 1
        if scan_count >= 3:
            stop.set()
        return iter(_fake_png_entries(1))

    monkeypatch.setattr("web.jobs.os.scandir", fake_scandir)

    events = await _collect_progress(
        mgr,
        job_id,
        watch_upscale_progress(
            mgr,
            job_id,
            tmp_path / "upscaled",
            frame_count=4,
            stop_event=stop,
            poll_interval=0,
        ),
    )

    assert [(event.current, event.total) for event in events] == [(1, 4)]


@pytest.mark.asyncio
async def test_watch_upscale_progress_caps_count_at_frame_count(tmp_path, monkeypatch):
    mgr, job_id = _register_job(tmp_path)
    stop = asyncio.Event()

    def fake_scandir(_path):
        stop.set()
        return iter(_fake_png_entries(7))

    monkeypatch.setattr("web.jobs.os.scandir", fake_scandir)

    events = await _collect_progress(
        mgr,
        job_id,
        watch_upscale_progress(
            mgr,
            job_id,
            tmp_path / "upscaled",
            frame_count=4,
            stop_event=stop,
            poll_interval=0,
        ),
    )

    assert [(event.current, event.total) for event in events] == [(4, 4)]
    assert mgr.get_job(job_id)["stage_progress"]["upscaling"] == {"current": 4, "total": 4}


@pytest.mark.asyncio
async def test_watch_upscale_progress_emits_final_count_after_stop(tmp_path, monkeypatch):
    mgr, job_id = _register_job(tmp_path)
    stop = asyncio.Event()
    first_scan_done = asyncio.Event()
    scan_count = 0

    def fake_scandir(_path):
        nonlocal scan_count
        scan_count += 1
        if scan_count == 1:
            first_scan_done.set()
            return iter(_fake_png_entries(0))
        return iter(_fake_png_entries(1))

    monkeypatch.setattr("web.jobs.os.scandir", fake_scandir)

    async def run_watcher():
        watcher = asyncio.create_task(
            watch_upscale_progress(
                mgr,
                job_id,
                tmp_path / "upscaled",
                frame_count=4,
                stop_event=stop,
                poll_interval=60,
            )
        )
        await first_scan_done.wait()
        stop.set()
        await watcher

    events = await _collect_progress(mgr, job_id, run_watcher())

    assert [(event.current, event.total) for event in events] == [(1, 4)]
