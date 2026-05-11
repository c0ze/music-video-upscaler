"""Cancellation tests for JobManager.

These tests exercise the cancel pathway end-to-end at the JobManager layer,
which is what the HTTP handler at /api/jobs/{id}/cancel relies on:

  - cancel_active_run() must SIGTERM the live stage subprocess so a long
    upscale stops within seconds (B1 regression).
  - When cancel races a stage transition, the orchestrator's exception
    handler must NOT publish an ErrorEvent on top of the user's cancel
    (I3 regression).
"""
from __future__ import annotations

import asyncio
import sys
import time

import pytest

from web.events import ErrorEvent, LogEvent
from web.jobs import JobManager
from web.state import IllegalTransition, JobState
from web.subprocess_runner import StageRun


@pytest.mark.asyncio
async def test_cancel_active_run_terminates_live_subprocess(tmp_path):
    """A long-running stage must be killed by cancel_active_run, not waited for."""
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full", url="https://example.test/v",
        model="realesr-general-x4v3", scale=4, output_format="mkv",
    )
    log_path = mgr.workdir.log_path(job_id)

    if sys.platform == "win32":
        cmd = ["cmd", "/c", "ping", "-n", "60", "127.0.0.1"]
    else:
        cmd = ["sleep", "60"]

    run = StageRun(cmd=cmd, cwd=workdir, log_path=log_path)
    runner = asyncio.create_task(mgr._run_tracked(job_id, run))

    # Wait until the subprocess is actually alive and registered as active.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if mgr._active_runs.get(job_id) is run and run.process is not None:
            break
        await asyncio.sleep(0.05)
    assert run.process is not None, "stage subprocess never started"
    assert run.process.returncode is None, "stage exited before we could cancel"

    started = time.monotonic()
    cancelled = await mgr.cancel_active_run(job_id, grace_seconds=2.0)
    assert cancelled is True

    rc = await asyncio.wait_for(runner, timeout=5.0)
    elapsed = time.monotonic() - started

    assert rc != 0, "subprocess should have exited with a non-zero rc when killed"
    assert elapsed < 4.0, f"cancel took {elapsed:.1f}s; should kill within grace+slop"
    assert run.was_cancelled is True
    # And the active-runs slot must be released by _run_tracked's finally.
    assert mgr._active_runs.get(job_id) is None


@pytest.mark.asyncio
async def test_cancel_active_run_returns_false_when_no_stage_running(tmp_path):
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="https://example.test/v",
        model="realesr-general-x4v3", scale=4, output_format="mkv",
    )
    assert await mgr.cancel_active_run(job_id) is False


@pytest.mark.asyncio
async def test_cancel_race_does_not_publish_error_event(tmp_path):
    """When the cancel handler beats the orchestrator to a state transition,
    the orchestrator's exception handler must keep its mouth shut: no
    ErrorEvent should follow the user's cancel.
    """
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full", url="https://example.test/v",
        model="realesr-general-x4v3", scale=4, output_format="mkv",
    )

    sub = await mgr.subscribe(job_id)
    received: list = []

    async def drain() -> None:
        async for evt in sub:
            received.append(evt)

    drain_task = asyncio.create_task(drain())

    # Drive a stage forward, then simulate the cancel handler racing.
    mgr.set_state(job_id, JobState.DOWNLOADING)
    mgr.set_state(job_id, JobState.CANCELLED)

    # Now mimic exactly the orchestrator's exception-handler block that runs
    # when run_stage raises after the cancel. The except branch we're
    # exercising lives in run_full_job and run_preview_job alike.
    exc = RuntimeError("upscaling failed")
    mgr.set_error(job_id, str(exc))
    try:
        mgr.set_state(job_id, JobState.FAILED)
    except IllegalTransition:
        pass
    else:
        await mgr.publish(
            job_id, ErrorEvent(stage="upscaling", message=str(exc))
        )

    await mgr.close_subscribers(job_id)
    await asyncio.wait_for(drain_task, timeout=2.0)

    error_events = [e for e in received if isinstance(e, ErrorEvent)]
    assert error_events == [], (
        "no ErrorEvent should be published when cancel preempts FAILED; "
        f"got: {error_events!r}"
    )


@pytest.mark.asyncio
async def test_set_state_releases_active_slot_on_terminal(tmp_path):
    """A terminal transition must clear _active_job_id so the next submission is accepted."""
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="https://example.test/v",
        model="realesr-general-x4v3", scale=4, output_format="mkv",
    )
    assert mgr._active_job_id == job_id

    mgr.set_state(job_id, JobState.DOWNLOADING)
    mgr.set_state(job_id, JobState.CANCELLED)

    assert mgr._active_job_id is None, "terminal transition must release the slot"

    # Submitting a fresh job must now succeed without raising.
    mgr.register_job(
        kind="full", url="https://example.test/v2",
        model="realesr-general-x4v3", scale=4, output_format="mkv",
    )
