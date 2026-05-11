"""JobManager: data model, persistence, pub/sub. Orchestration lives in run_full_job()."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Tuple

from web.events import (
    CompleteEvent,
    ErrorEvent,
    LogEvent,
    ProgressEvent,
    StageEvent,
    ThumbnailEvent,
)
from web.live_watcher import watch_upscale_dir
from web.platform_info import REPO_ROOT, stage_command
from web.state import IllegalTransition, JobState, can_transition
from web.subprocess_runner import StageRun, run_stage
from web.thumbnails import ThumbnailGenerator
from web.workdir import WorkdirManager

Event = Any  # one of the *Event dataclasses from web.events

_log = logging.getLogger(__name__)


@dataclass
class JobRecord:
    job_id: str
    kind: str
    state: str
    url: str
    model: str
    scale: int
    output_format: str
    audio_override: Optional[str]
    started_at: str
    stage_progress: Dict[str, Dict[str, int]] = field(default_factory=dict)
    output_path: Optional[str] = None
    error: Optional[str] = None
    pid: Optional[int] = None


class JobManager:
    def __init__(self, workdir_root: Optional[Path] = None) -> None:
        self.workdir = WorkdirManager(root=workdir_root)
        self._records: Dict[str, JobRecord] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._active_job_id: Optional[str] = None

    # --- registration -------------------------------------------------

    def register_job(
        self,
        *,
        kind: str,
        url: str,
        model: str,
        scale: int,
        output_format: str,
        audio_override: Optional[str] = None,
    ) -> Tuple[str, Path]:
        if self._active_job_id is not None:
            active = self._records.get(self._active_job_id)
            if active and not JobState(active.state).is_terminal():
                raise RuntimeError(f"a job is already active: {self._active_job_id}")
        job_id, workdir = self.workdir.create_job()
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            state=JobState.CREATED.value,
            url=url,
            model=model,
            scale=scale,
            output_format=output_format,
            audio_override=audio_override,
            started_at=datetime.now().astimezone().isoformat(),
        )
        self._records[job_id] = record
        self._active_job_id = job_id
        self._persist(job_id)
        return job_id, workdir

    # --- state --------------------------------------------------------

    def set_state(self, job_id: str, new_state: JobState) -> None:
        rec = self._records[job_id]
        cur = JobState(rec.state)
        if not can_transition(cur, new_state):
            raise IllegalTransition(cur, new_state)
        rec.state = new_state.value
        self._persist(job_id)

    def set_progress(self, job_id: str, stage: str, current: int, total: int) -> None:
        rec = self._records[job_id]
        rec.stage_progress[stage] = {"current": current, "total": total}
        self._persist(job_id)

    def set_output(self, job_id: str, output_path: Path) -> None:
        self._records[job_id].output_path = str(output_path)
        self._persist(job_id)

    def set_error(self, job_id: str, message: str) -> None:
        self._records[job_id].error = message
        self._persist(job_id)

    def set_pid(self, job_id: str, pid: Optional[int]) -> None:
        self._records[job_id].pid = pid
        self._persist(job_id)

    def set_audio_override(self, job_id: str, relative_name: str) -> None:
        self._records[job_id].audio_override = relative_name
        self._persist(job_id)

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return asdict(self._records[job_id])

    def get_workdir(self, job_id: str) -> Path:
        return self.workdir.get_workdir(job_id)

    # --- pub/sub ------------------------------------------------------

    async def subscribe(self, job_id: str) -> AsyncIterator[Event]:
        if job_id not in self._records:
            raise KeyError(job_id)
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subscribers.setdefault(job_id, []).append(q)

        async def gen() -> AsyncIterator[Event]:
            try:
                while True:
                    evt = await q.get()
                    if evt is None:
                        return
                    yield evt
            finally:
                try:
                    self._subscribers[job_id].remove(q)
                except (KeyError, ValueError):
                    pass

        return gen()

    async def publish(self, job_id: str, event: Event) -> None:
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                _log.warning("subscriber queue full for job %s; dropping event %s",
                             job_id, type(event).__name__)

    async def close_subscribers(self, job_id: str) -> None:
        for q in list(self._subscribers.get(job_id, [])):
            # Drain oldest entries until the sentinel fits, so a slow consumer
            # cannot prevent shutdown.
            while True:
                try:
                    q.put_nowait(None)
                    break
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        break

    # --- persistence --------------------------------------------------

    def _persist(self, job_id: str) -> None:
        rec = self._records[job_id]
        path = self.workdir.state_path(job_id)
        payload = json.dumps(asdict(rec), indent=2)
        # Atomic write: tmp file in the same dir, then os.replace.
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=".state.", dir=str(path.parent))
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(payload)
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # --- orchestration ------------------------------------------------

    async def run_full_job(
        self,
        job_id: str,
        output_dir: Path,
        thumb_every_n: int = 200,
        on_thumbnail: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        rec = self._records[job_id]
        workdir = self.workdir.get_workdir(job_id)
        log = self.workdir.log_path(job_id)
        source_dir = workdir / "source"
        frames_dir = workdir / "tmp_frames"
        upscaled_dir = workdir / f"tmp_upscaled_{rec.scale}x"
        out_workdir = workdir / "output"
        out_workdir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        async def _line(line: str) -> None:
            await self.publish(job_id, LogEvent(line=line))

        async def _stage_started(name: str, internal: JobState) -> None:
            self.set_state(job_id, internal)
            await self.publish(job_id, StageEvent(stage=internal.value, status="started"))

        async def _stage_done(internal: JobState, extra: Optional[Dict[str, Any]] = None) -> None:
            await self.publish(
                job_id,
                StageEvent(stage=internal.value, status="done", extra=extra or {}),
            )

        try:
            # 1) DOWNLOAD via yt-dlp directly (server-owned stage)
            await _stage_started("downloading", JobState.DOWNLOADING)
            ytdlp = shutil.which("yt-dlp") or "yt-dlp"
            video_template = str(source_dir / "video.%(ext)s")
            audio_template = str(source_dir / "audio.%(ext)s")
            dl_cmd = [
                ytdlp, "--no-warnings",
                "-f", "bv*+ba/b", "--merge-output-format", "mkv",
                "-o", video_template, rec.url,
            ]
            run = StageRun(cmd=dl_cmd, cwd=source_dir, log_path=log, on_line=_line)
            self.set_pid(job_id, None)
            rc = await run_stage(run)
            self.set_pid(job_id, run.process.pid if run.process else None)
            if rc != 0:
                raise RuntimeError("downloading failed")

            # Audio: user override > yt-dlp -x
            if rec.audio_override:
                audio_path = workdir / rec.audio_override
            else:
                audio_dl_cmd = [
                    ytdlp, "--no-warnings", "-x", "--audio-format", "best",
                    "-o", audio_template, rec.url,
                ]
                run = StageRun(cmd=audio_dl_cmd, cwd=source_dir, log_path=log, on_line=_line)
                rc = await run_stage(run)
                if rc != 0:
                    raise RuntimeError("downloading audio failed")
                audio_path = next(source_dir.glob("audio.*"))
            video_path = next(source_dir.glob("video.*"))
            await _stage_done(JobState.DOWNLOADING, {"video": video_path.name, "audio": audio_path.name})

            # 2) PREPARING = sanitize + sync_audio
            await _stage_started("preparing", JobState.PREPARING)
            sync_cmd = stage_command("sync_audio", [str(video_path), str(audio_path), rec.url])
            run = StageRun(cmd=sync_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line)
            rc = await run_stage(run)
            if rc != 0:
                raise RuntimeError("preparing failed")
            synced_audio = video_path.with_name(f"{video_path.stem}_synced.flac")
            await _stage_done(JobState.PREPARING, {"synced_audio": synced_audio.name})

            # 3) EXTRACT
            await _stage_started("extracting", JobState.EXTRACTING)
            ext_cmd = stage_command("extract", [str(video_path), str(frames_dir)])
            run = StageRun(cmd=ext_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line)
            rc = await run_stage(run)
            if rc != 0:
                raise RuntimeError("extracting failed")
            frame_count = sum(1 for _ in frames_dir.glob("*.png"))
            self.set_progress(job_id, "extract", frame_count, frame_count)
            await _stage_done(JobState.EXTRACTING, {"frame_count": frame_count})

            # 4) UPSCALE (with live thumbnail watcher)
            await _stage_started("upscaling", JobState.UPSCALING)
            stop = asyncio.Event()
            thumbgen = ThumbnailGenerator()

            async def _on_frame(frame_id: str) -> None:
                src = upscaled_dir / f"{frame_id}.png"
                if not src.is_file():
                    return
                dst = workdir / "thumbs" / f"up_{frame_id}.jpg"
                try:
                    await thumbgen.generate(src, dst)
                except Exception:
                    return
                self.set_progress(job_id, "upscale", int(frame_id), frame_count)
                await self.publish(
                    job_id,
                    ThumbnailEvent(
                        frame_id=frame_id, kind="up",
                        url=f"/api/jobs/{job_id}/frames/up/{frame_id}",
                    ),
                )
                if on_thumbnail:
                    await on_thumbnail(frame_id)

            watcher = asyncio.create_task(
                watch_upscale_dir(upscaled_dir, thumb_every_n, _on_frame, stop, poll_interval=1.0)
            )
            up_cmd = stage_command(
                "upscale",
                [str(frames_dir), str(upscaled_dir), str(rec.scale), rec.model],
            )
            run = StageRun(cmd=up_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line)
            try:
                rc = await run_stage(run)
            finally:
                stop.set()
                await watcher
            if rc != 0:
                raise RuntimeError("upscaling failed")
            await _stage_done(JobState.UPSCALING)

            # 5) MUX
            await _stage_started("muxing", JobState.MUXING)
            output_name = (
                f"{video_path.stem}_realesrgan_{rec.model}_{rec.scale}x_HQ.{rec.output_format}"
            )
            internal_out = out_workdir / output_name
            mux_cmd = stage_command(
                "mux", [str(upscaled_dir), str(synced_audio), str(internal_out), str(video_path)],
            )
            run = StageRun(cmd=mux_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line)
            rc = await run_stage(run)
            if rc != 0:
                raise RuntimeError("muxing failed")

            # Symlink (or copy on Windows) into user-visible output dir
            final_dest = output_dir / output_name
            try:
                if final_dest.exists() or final_dest.is_symlink():
                    final_dest.unlink()
                final_dest.symlink_to(internal_out)
            except (OSError, NotImplementedError):
                shutil.copy2(internal_out, final_dest)

            self.set_output(job_id, final_dest)
            self.set_state(job_id, JobState.COMPLETE)
            size = internal_out.stat().st_size
            await self.publish(job_id, CompleteEvent(output=str(final_dest), size_bytes=size))

        except Exception as exc:
            self.set_error(job_id, str(exc))
            try:
                self.set_state(job_id, JobState.FAILED)
            except IllegalTransition:
                pass
            await self.publish(job_id, ErrorEvent(stage=rec.state, message=str(exc)))
        finally:
            await self.close_subscribers(job_id)
