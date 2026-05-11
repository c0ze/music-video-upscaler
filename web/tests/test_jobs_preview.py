import asyncio
from pathlib import Path

import pytest

from web.events import ThumbnailEvent
from web.jobs import JobManager
from web.state import JobState


def _patch_preview(monkeypatch):
    from web import jobs as jobs_module

    async def fake_run_stage(run):
        cmd = run.cmd
        run.process = type("P", (), {"returncode": 0, "pid": 1})()
        if cmd[0].endswith("yt-dlp") or cmd[0] == "yt-dlp":
            # write a tiny mp4
            (run.cwd / "video.mp4").write_bytes(b"\x00" * 64)
            return 0
        if "02_extract" in cmd[0]:
            frames_dir = Path(cmd[2])
            frames_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, 6):
                (frames_dir / f"{i:06d}.png").write_bytes(b"\x00" * 32)
            return 0
        if "03_upscale" in cmd[0]:
            up_dir = Path(cmd[2])
            up_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, 6):
                (up_dir / f"{i:06d}.png").write_bytes(b"\x00" * 32)
            return 0
        return 0

    monkeypatch.setattr(jobs_module, "run_stage", fake_run_stage)

    async def fake_generate(self, src, dst, width=360):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"\xff\xd8\xff")  # fake JPEG header

    monkeypatch.setattr(jobs_module.ThumbnailGenerator, "generate", fake_generate)


@pytest.mark.asyncio
async def test_run_preview_job_extracts_5_frames(tmp_path, monkeypatch):
    _patch_preview(monkeypatch)
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="preview", url="https://x.test/v", model="m",
        scale=4, output_format="mkv",
    )

    await mgr.run_preview_job(job_id)

    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.COMPLETE.value
    thumbs = list((workdir / "thumbs").iterdir())
    assert len(thumbs) >= 10  # 5 src + 5 up
