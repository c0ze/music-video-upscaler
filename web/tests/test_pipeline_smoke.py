"""End-to-end smoke test against the real stage scripts on a tiny synthetic video.

Skipped automatically if any required external tool or model is missing
(ffmpeg / ffprobe / realesrgan-ncnn-vulkan / default model). When all are present
this exercises sync_audio -> extract -> upscale -> mux on a 2s 64x36 clip and
verifies a non-empty muxed output.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


def _has(tool: str) -> bool:
    return shutil.which(tool) is not None


def _has_realesrgan() -> bool:
    candidates = [
        REPO_ROOT / "tools" / "realesrgan-ncnn-vulkan",
        REPO_ROOT / "windows" / "realesrgan-ncnn-vulkan.exe",
    ]
    return shutil.which("realesrgan-ncnn-vulkan") is not None or any(p.exists() for p in candidates)


def _has_default_model() -> bool:
    md = REPO_ROOT / "models"
    return (md / "realesr-general-x4v3.param").is_file() and (md / "realesr-general-x4v3.bin").is_file()


pytestmark = pytest.mark.skipif(
    not (_has("ffmpeg") and _has("ffprobe") and _has_realesrgan() and _has_default_model()),
    reason="external tools or default model missing",
)


@pytest.fixture(scope="module")
def tiny_video() -> Path:
    """Synthesize a 2s 64x36 test pattern + silent audio (cached on disk)."""
    out = FIXTURES / "tiny.mkv"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=64x36:rate=10:duration=2",
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", "2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    return out


@pytest.mark.asyncio
async def test_full_pipeline_against_tiny_video(tiny_video, tmp_path):
    from web.jobs import JobManager
    from web.platform_info import REPO_ROOT as REPO, stage_command
    from web.state import JobState
    from web.subprocess_runner import StageRun, run_stage

    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full",
        url="local://tiny",
        model="realesr-general-x4v3",
        scale=4,
        output_format="mkv",
    )
    src_dir = workdir / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tiny_video, src_dir / "video.mkv")
    # Pull audio out for the sync stage to consume.
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y", "-i", str(tiny_video),
            "-vn", "-c:a", "flac", str(src_dir / "audio.flac"),
        ],
        check=True,
        capture_output=True,
    )

    async def _swallow(_line: str) -> None:
        return None

    log_path = mgr.workdir.log_path(job_id)

    # CREATED -> DOWNLOADING -> PREPARING (no real download; we pre-seeded).
    mgr.set_state(job_id, JobState.DOWNLOADING)
    mgr.set_state(job_id, JobState.PREPARING)

    rc = await run_stage(StageRun(
        cmd=stage_command("sync_audio", [str(src_dir / "video.mkv"), str(src_dir / "audio.flac")]),
        cwd=REPO,
        log_path=log_path,
        on_line=_swallow,
    ))
    assert rc == 0
    synced = src_dir / "video_synced.flac"
    assert synced.is_file(), "sync_audio should produce <basename>_synced.flac next to the input video"

    mgr.set_state(job_id, JobState.EXTRACTING)
    frames = workdir / "tmp_frames"
    rc = await run_stage(StageRun(
        cmd=stage_command("extract", [str(src_dir / "video.mkv"), str(frames)]),
        cwd=REPO,
        log_path=log_path,
        on_line=_swallow,
    ))
    assert rc == 0
    assert any(frames.glob("*.png")), "extract should produce PNG frames"

    mgr.set_state(job_id, JobState.UPSCALING)
    upscaled = workdir / "tmp_upscaled_4x"
    rc = await run_stage(StageRun(
        cmd=stage_command("upscale", [str(frames), str(upscaled), "4", "realesr-general-x4v3"]),
        cwd=REPO,
        log_path=log_path,
        on_line=_swallow,
    ))
    assert rc == 0
    assert any(upscaled.glob("*.png")), "upscale should produce upscaled PNG frames"

    mgr.set_state(job_id, JobState.MUXING)
    out = workdir / "output" / "tiny_upscaled.mkv"
    rc = await run_stage(StageRun(
        cmd=stage_command("mux", [str(upscaled), str(synced), str(out), str(src_dir / "video.mkv")]),
        cwd=REPO,
        log_path=log_path,
        on_line=_swallow,
    ))
    assert rc == 0
    assert out.is_file(), "mux should produce the final output file"
    assert out.stat().st_size > 0

    mgr.set_state(job_id, JobState.COMPLETE)
    assert JobState(mgr.get_job(job_id)["state"]) is JobState.COMPLETE
