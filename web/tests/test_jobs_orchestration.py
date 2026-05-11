import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from web.events import CompleteEvent, ErrorEvent, StageEvent
from web.jobs import JobManager
from web.state import JobState


def _patch_stages(monkeypatch, *, fail_at: str = ""):
    """Patch run_stage so it just touches expected output and returns 0 (or 1 at fail_at)."""
    from web import jobs as jobs_module

    async def fake_run_stage(run):
        # Simulate the stage having succeeded by creating its expected output.
        cmd = run.cmd
        run.process = type("P", (), {"returncode": 0, "pid": 12345})()
        if "yt-dlp" in cmd[0] or cmd[0].endswith("yt-dlp"):
            (run.cwd / "video.mp4").write_bytes(b"\x00")
            (run.cwd / "audio.m4a").write_bytes(b"\x00")
            stage = "download"
        elif "01_sync_audio" in cmd[0]:
            video = Path(cmd[1])
            (video.parent / f"{video.stem}_synced.flac").write_bytes(b"\x00")
            stage = "sync_audio"
        elif "02_extract" in cmd[0]:
            frames_dir = Path(cmd[2])
            frames_dir.mkdir(parents=True, exist_ok=True)
            (frames_dir / "000001.png").write_bytes(b"\x00")
            stage = "extract"
        elif "03_upscale" in cmd[0]:
            up_dir = Path(cmd[2])
            up_dir.mkdir(parents=True, exist_ok=True)
            (up_dir / "000001.png").write_bytes(b"\x00")
            stage = "upscale"
        elif "04_mux" in cmd[0]:
            output = Path(cmd[3])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"\x00" * 1024)
            stage = "mux"
        elif "00_sanitize" in cmd[0]:
            stage = "sanitize"
        else:
            stage = "?"

        return 1 if stage == fail_at else 0

    monkeypatch.setattr(jobs_module, "run_stage", fake_run_stage)


@pytest.mark.asyncio
async def test_run_full_job_happy_path(tmp_path, monkeypatch):
    _patch_stages(monkeypatch)
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full", url="https://x.test/v", model="realesr-general-x4v3",
        scale=4, output_format="mkv",
    )
    out_dir = tmp_path / "out"
    await mgr.run_full_job(job_id, output_dir=out_dir)

    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.COMPLETE.value
    assert snap["output_path"]
    assert Path(snap["output_path"]).is_file()


@pytest.mark.asyncio
async def test_run_full_job_failure_marks_failed(tmp_path, monkeypatch):
    _patch_stages(monkeypatch, fail_at="upscale")
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="https://x.test/v", model="m",
        scale=4, output_format="mkv",
    )
    await mgr.run_full_job(job_id, output_dir=tmp_path / "out")

    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.FAILED.value
    assert "upscale" in (snap["error"] or "").lower()


@pytest.mark.asyncio
async def test_run_full_job_publishes_stage_events(tmp_path, monkeypatch):
    _patch_stages(monkeypatch)
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="u", model="m", scale=4, output_format="mkv",
    )

    events = []
    sub = await mgr.subscribe(job_id)

    async def collect():
        async for e in sub:
            events.append(e)

    collector = asyncio.create_task(collect())
    await mgr.run_full_job(job_id, output_dir=tmp_path / "out")
    await asyncio.sleep(0.05)
    collector.cancel()

    stages = [getattr(e, "stage", None) for e in events if isinstance(e, StageEvent)]
    assert "downloading" in stages
    assert "upscaling" in stages
    assert "muxing" in stages
    assert any(isinstance(e, CompleteEvent) for e in events)
