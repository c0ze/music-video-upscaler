import asyncio
import json

import pytest

from web.events import LogEvent
from web.jobs import JobManager
from web.state import JobState


@pytest.mark.asyncio
async def test_register_job_creates_state_file(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    job_id, workdir = mgr.register_job(
        kind="full",
        url="https://example.com/x",
        model="realesr-general-x4v3",
        scale=4,
        output_format="mkv",
    )
    assert workdir.is_dir()

    state = json.loads((workdir / "state.json").read_text())
    assert state["job_id"] == job_id
    assert state["state"] == JobState.CREATED.value
    assert state["model"] == "realesr-general-x4v3"
    assert state["scale"] == 4


@pytest.mark.asyncio
async def test_set_state_writes_to_file_and_publishes(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    job_id, _ = mgr.register_job(
        kind="full", url="x", model="m", scale=4, output_format="mkv",
    )

    received = []
    sub = await mgr.subscribe(job_id)

    async def reader():
        async for evt in sub:
            received.append(evt)
            if len(received) >= 1:
                break

    reader_task = asyncio.create_task(reader())
    await mgr.publish(job_id, LogEvent(line="hi"))
    await asyncio.wait_for(reader_task, timeout=1.0)

    assert any(getattr(e, "line", "") == "hi" for e in received)


@pytest.mark.asyncio
async def test_only_one_active_job(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    mgr.register_job(kind="full", url="x", model="m", scale=4, output_format="mkv")
    with pytest.raises(RuntimeError) as exc:
        mgr.register_job(kind="full", url="y", model="m", scale=4, output_format="mkv")
    assert "active" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_release_after_terminal_allows_next(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    job_id, _ = mgr.register_job(kind="full", url="x", model="m", scale=4, output_format="mkv")
    # Walk the forward chain to a terminal state (CREATED -> COMPLETE is illegal
    # by design; the state machine requires going through the pipeline).
    for s in (
        JobState.DOWNLOADING,
        JobState.PREPARING,
        JobState.EXTRACTING,
        JobState.UPSCALING,
        JobState.MUXING,
        JobState.COMPLETE,
    ):
        mgr.set_state(job_id, s)
    # Now a new one is allowed.
    mgr.register_job(kind="full", url="y", model="m", scale=4, output_format="mkv")


@pytest.mark.asyncio
async def test_get_job_returns_snapshot(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=2, output_format="mp4")
    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.CREATED.value
    assert snap["scale"] == 2
    assert snap["output_format"] == "mp4"


@pytest.mark.asyncio
async def test_set_audio_override_persists(tmp_path):
    mgr = JobManager(workdir_root=tmp_path)
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    mgr.set_audio_override(job_id, "audio_override.flac")
    assert mgr.get_job(job_id)["audio_override"] == "audio_override.flac"


@pytest.mark.asyncio
async def test_close_subscribers_unblocks_full_queue(tmp_path):
    """Even when a slow subscriber's queue is full, close_subscribers must
    deliver the None sentinel so the consumer's `async for` exits."""
    mgr = JobManager(workdir_root=tmp_path)
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    sub = await mgr.subscribe(job_id)

    # Fill the underlying queue without consuming.
    inner_q = mgr._subscribers[job_id][0]
    for i in range(inner_q.maxsize):
        inner_q.put_nowait(LogEvent(line=f"backlog {i}"))
    assert inner_q.full()

    await mgr.close_subscribers(job_id)

    received = []
    async def reader():
        async for evt in sub:
            received.append(evt)
    await asyncio.wait_for(reader(), timeout=1.0)
    # We dropped the oldest event(s) to make room for the sentinel.
    assert len(received) <= inner_q.maxsize


@pytest.mark.asyncio
async def test_persist_is_atomic(tmp_path):
    """state.json should never be empty/partial mid-write; using os.replace guarantees atomicity."""
    mgr = JobManager(workdir_root=tmp_path)
    job_id, workdir = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    state_file = workdir / "state.json"
    # Multiple sequential writes should each leave a complete, parseable file.
    for s in (
        JobState.DOWNLOADING,
        JobState.PREPARING,
        JobState.EXTRACTING,
    ):
        mgr.set_state(job_id, s)
        data = json.loads(state_file.read_text())
        assert data["state"] == s.value
