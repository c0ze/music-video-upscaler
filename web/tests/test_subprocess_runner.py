import asyncio
import sys
from pathlib import Path

import pytest

from web.subprocess_runner import StageRun, run_stage


@pytest.mark.asyncio
async def test_run_stage_captures_stdout_and_returns_zero(tmp_path):
    log = tmp_path / "log.txt"
    lines = []

    async def on_line(line: str) -> None:
        lines.append(line)

    run = StageRun(
        cmd=[sys.executable, "-c", "print('hello'); print('world')"],
        cwd=tmp_path,
        log_path=log,
        on_line=on_line,
    )
    rc = await run_stage(run)

    assert rc == 0
    assert "hello" in lines
    assert "world" in lines
    assert "hello" in log.read_text()
    assert "world" in log.read_text()


@pytest.mark.asyncio
async def test_run_stage_returns_nonzero_on_failure(tmp_path):
    run = StageRun(
        cmd=[sys.executable, "-c", "import sys; sys.exit(7)"],
        cwd=tmp_path,
        log_path=tmp_path / "log.txt",
        on_line=None,
    )
    assert await run_stage(run) == 7


@pytest.mark.asyncio
async def test_run_stage_cancel_terminates_process(tmp_path):
    run = StageRun(
        cmd=[sys.executable, "-c", "import time; [time.sleep(0.1) for _ in range(100)]"],
        cwd=tmp_path,
        log_path=tmp_path / "log.txt",
        on_line=None,
    )

    task = asyncio.create_task(run_stage(run))
    await asyncio.sleep(0.2)
    await run.cancel(grace_seconds=1.0)
    rc = await task
    assert rc != 0
    assert run.was_cancelled is True


@pytest.mark.asyncio
async def test_run_stage_captures_stderr(tmp_path):
    lines = []

    async def on_line(line: str) -> None:
        lines.append(line)

    run = StageRun(
        cmd=[sys.executable, "-c", "import sys; print('err', file=sys.stderr)"],
        cwd=tmp_path,
        log_path=tmp_path / "log.txt",
        on_line=on_line,
    )
    rc = await run_stage(run)
    assert rc == 0
    assert any("err" in line for line in lines)
