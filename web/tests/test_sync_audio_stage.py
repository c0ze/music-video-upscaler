import shutil
import subprocess
from pathlib import Path

import pytest

from web.platform_info import REPO_ROOT, stage_command

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


def _make_video_with_audio_delay(path: Path, *, delay_ms: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=24:d=0.9",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=0.5",
            "-filter_complex",
            f"[1:a]aformat=channel_layouts=stereo,adelay={delay_ms}|{delay_ms}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _make_flac_with_audio_delay(path: Path, *, delay_ms: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=0.5",
            "-af",
            f"aformat=channel_layouts=stereo,adelay={delay_ms}|{delay_ms}",
            "-c:a",
            "flac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe required")
def test_sync_audio_prepends_finite_silence(tmp_path):
    video = tmp_path / "video.mkv"
    audio = tmp_path / "audio.flac"
    synced = tmp_path / "video_synced.flac"
    _make_video_with_audio_delay(video, delay_ms=400)
    _make_flac_with_audio_delay(audio, delay_ms=100)

    subprocess.run(
        stage_command("sync_audio", [str(video), str(audio)]),
        cwd=REPO_ROOT,
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    )

    assert synced.is_file()
    duration = _probe_duration(synced)
    assert 0.75 <= duration <= 1.05
    assert synced.stat().st_size < 5_000_000
