"""Async subprocess runner with line streaming, log capture, and cooperative cancel."""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional


LineHandler = Optional[Callable[[str], Awaitable[None]]]


@dataclass
class StageRun:
    cmd: List[str]
    cwd: Path
    log_path: Path
    on_line: LineHandler = None
    env: Optional[Dict[str, str]] = None
    process: Optional[asyncio.subprocess.Process] = field(default=None, init=False)
    was_cancelled: bool = field(default=False, init=False)

    async def cancel(self, grace_seconds: float = 10.0) -> None:
        proc = self.process
        if proc is None or proc.returncode is not None:
            return
        self.was_cancelled = True
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return

        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            try:
                if sys.platform == "win32":
                    proc.kill()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


async def run_stage(run: StageRun) -> int:
    run.log_path.parent.mkdir(parents=True, exist_ok=True)

    creation_kwargs: Dict[str, object] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
        "cwd": str(run.cwd),
    }
    if run.env is not None:
        creation_kwargs["env"] = run.env
    if sys.platform != "win32":
        creation_kwargs["preexec_fn"] = os.setsid

    proc = await asyncio.create_subprocess_exec(*run.cmd, **creation_kwargs)
    run.process = proc

    assert proc.stdout is not None
    with run.log_path.open("ab") as logf:
        while True:
            chunk = await proc.stdout.readline()
            if not chunk:
                break
            logf.write(chunk)
            logf.flush()
            line = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
            if run.on_line is not None and line:
                try:
                    await run.on_line(line)
                except Exception:
                    pass

    return await proc.wait()
