"""JobManager: data model, persistence, pub/sub. Orchestration lives in run_full_job()."""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from web.events import (
    CompleteEvent, ErrorEvent, LogEvent, ProgressEvent, StageEvent, ThumbnailEvent,
)
from web.state import IllegalTransition, JobState, can_transition
from web.workdir import WorkdirManager

Event = Any  # one of the *Event dataclasses from web.events


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
        self._lock = asyncio.Lock()

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
                pass

    async def close_subscribers(self, job_id: str) -> None:
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # --- persistence --------------------------------------------------

    def _persist(self, job_id: str) -> None:
        rec = self._records[job_id]
        path = self.workdir.state_path(job_id)
        path.write_text(json.dumps(asdict(rec), indent=2))
