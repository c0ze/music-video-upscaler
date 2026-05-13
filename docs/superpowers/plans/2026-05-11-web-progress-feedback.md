# Web Progress Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the web job panel show stage-local progress instead of a static `Starting…`, while keeping live thumbnails sampled and lightweight.

**Architecture:** Keep the current SSE event model and existing progress bar/text UI. Update the frontend to render immediate stage labels for stages without totals, add a small backend progress watcher that emits `ProgressEvent`s from actual completed upscaled frame counts, and keep thumbnail publishing sampled at a lower cadence than progress updates by deriving a larger thumbnail stride from the extracted frame count.

**Tech Stack:** FastAPI static asset tests, pytest + asyncio, vanilla JavaScript, Python async job orchestration, SSE `stage` / `progress` / `thumbnail` events

---

## File map

- `web/static/app.js`: replace the stale `Starting…` text with stage labels and format numeric stage-local progress consistently.
- `web/jobs.py`: add a focused upscale-progress watcher, derive a larger thumbnail stride from the extracted frame count, and wire both into `run_full_job()`.
- `web/tests/test_server_basic.py`: static-surface coverage for the new frontend stage-label strings and formatting helper.
- `web/tests/test_jobs_progress.py` (new): unit tests for thumbnail sampling stride and the new upscale-progress watcher.
- `web/tests/test_jobs_orchestration.py`: regression coverage that proves `run_full_job()` emits `ProgressEvent`s even when thumbnail sampling is too sparse to emit any thumbnails.

### Task 1: Frontend stage-label fallback

**Files:**
- Modify: `web/tests/test_server_basic.py`
- Modify: `web/static/app.js`
- Test: `web/tests/test_server_basic.py`

- [ ] **Step 1: Write the failing static-surface test**

Add this test near the other JS string coverage in `web/tests/test_server_basic.py`:

```python
def test_static_js_contains_stage_progress_labels(client):
    js = client.get("/static/app.js")
    assert js.status_code == 200
    body = js.text
    assert "Downloading..." in body
    assert "Syncing..." in body
    assert "Extracting..." in body
    assert "Upscaling..." in body
    assert "Muxing..." in body
    assert "function stageLabel" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py::test_static_js_contains_stage_progress_labels -v
```

Expected: FAIL because `app.js` does not yet define stage-label mapping or include those strings.

- [ ] **Step 3: Implement the minimal frontend fallback in `web/static/app.js`**

Add a small stage-label helper above `showProgressPanel()`:

```javascript
function stageLabel(stage) {
  switch (stage) {
    case "downloading":
      return "Downloading...";
    case "preparing":
      return "Syncing...";
    case "extracting":
      return "Extracting...";
    case "upscaling":
      return "Upscaling...";
    case "muxing":
      return "Muxing...";
    default:
      return "Starting...";
  }
}
```

Then update the `stage` and `progress` branches inside `handleEvent(evt)`:

```javascript
if (evt.type === "stage") {
  els.stages.forEach((li) => {
    if (li.dataset.stage === evt.stage) {
      if (evt.status === "done") {
        li.classList.remove("active");
        li.classList.add("done");
      } else {
        li.classList.add("active");
        els.progressBar.style.width = "0%";
        els.progressText.textContent = stageLabel(evt.stage);
      }
    }
  });
}

if (evt.type === "progress") {
  const pct = evt.total ? Math.round((evt.current / evt.total) * 100) : 0;
  const label = stageLabel(evt.stage).replace("...", "");
  els.progressBar.style.width = pct + "%";
  els.progressText.textContent = `${label} ${evt.current} / ${evt.total} (${pct}%)`;
}
```

- [ ] **Step 4: Run the focused test again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py::test_static_js_contains_stage_progress_labels -v
```

Expected: PASS

### Task 2: Backend progress watcher and thumbnail stride

**Files:**
- Create: `web/tests/test_jobs_progress.py`
- Modify: `web/jobs.py`
- Test: `web/tests/test_jobs_progress.py`

- [ ] **Step 1: Write the failing backend unit tests**

Create `web/tests/test_jobs_progress.py` with these tests:

```python
import asyncio

import pytest

from web.events import ProgressEvent
from web.jobs import JobManager, _thumbnail_stride, watch_upscale_progress


def test_thumbnail_stride_scales_down_thumbnail_frequency():
    assert _thumbnail_stride(frame_count=120) == 200
    assert _thumbnail_stride(frame_count=1600) == 200
    assert _thumbnail_stride(frame_count=4800) == 600


@pytest.mark.asyncio
async def test_watch_upscale_progress_emits_when_count_advances(tmp_path):
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    upscaled_dir = tmp_path / "upscaled"
    upscaled_dir.mkdir()
    stop = asyncio.Event()

    events = []
    sub = await mgr.subscribe(job_id)

    async def collect():
        async for event in sub:
            events.append(event)

    collector = asyncio.create_task(collect())

    async def producer():
        await asyncio.sleep(0.03)
        (upscaled_dir / "000001.png").write_bytes(b"x")
        await asyncio.sleep(0.03)
        (upscaled_dir / "000002.png").write_bytes(b"x")
        await asyncio.sleep(0.03)
        stop.set()

    watcher = asyncio.create_task(
        watch_upscale_progress(
            mgr,
            job_id,
            upscaled_dir,
            frame_count=4,
            stop_event=stop,
            poll_interval=0.01,
        )
    )
    await producer()
    await watcher
    await mgr.close_subscribers(job_id)
    await collector

    progress = [e for e in events if isinstance(e, ProgressEvent)]
    assert [(e.current, e.total) for e in progress] == [(1, 4), (2, 4)]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
web/.venv/bin/pytest web/tests/test_jobs_progress.py -v
```

Expected: FAIL because `_thumbnail_stride` and `watch_upscale_progress` do not exist yet.

- [ ] **Step 3: Implement the new helpers in `web/jobs.py`**

Add `math` to the imports and define these helpers near the top-level utility section:

```python
import math
```

```python
def _thumbnail_stride(frame_count: int, *, target_updates: int = 8, minimum: int = 200) -> int:
    if frame_count <= 0:
        return minimum
    return max(minimum, math.ceil(frame_count / target_updates))


async def watch_upscale_progress(
    manager: "JobManager",
    job_id: str,
    upscaled_dir: Path,
    frame_count: int,
    stop_event: asyncio.Event,
    poll_interval: float = 1.0,
) -> None:
    last_count = 0
    upscaled_dir.mkdir(parents=True, exist_ok=True)

    while not stop_event.is_set():
        try:
            count = sum(1 for e in os.scandir(upscaled_dir) if e.is_file() and e.name.endswith(".png"))
        except FileNotFoundError:
            count = 0

        count = min(count, frame_count)
        if count > last_count:
            manager.set_progress(job_id, "upscale", count, frame_count)
            await manager.publish(
                job_id,
                ProgressEvent(stage="upscale", current=count, total=frame_count),
            )
            last_count = count

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue
```

- [ ] **Step 4: Run the backend unit tests again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_jobs_progress.py -v
```

Expected: PASS

### Task 3: Wire real progress into `run_full_job()`

**Files:**
- Modify: `web/tests/test_jobs_orchestration.py`
- Modify: `web/jobs.py`
- Test: `web/tests/test_jobs_orchestration.py`

- [ ] **Step 1: Write the failing orchestration regression test**

Add this test to `web/tests/test_jobs_orchestration.py`:

```python
from web.events import ProgressEvent, ThumbnailEvent
```

```python
@pytest.mark.asyncio
async def test_run_full_job_emits_progress_even_when_thumbnails_are_sparse(tmp_path, monkeypatch):
    from web import jobs as jobs_module

    async def fake_run_stage(run):
        cmd = run.cmd
        run.process = type("P", (), {"returncode": 0, "pid": 12345})()
        if "yt-dlp" in cmd[0] or cmd[0].endswith("yt-dlp"):
            (run.cwd / "video.mp4").write_bytes(b"\x00")
            (run.cwd / "audio.m4a").write_bytes(b"\x00")
        elif "01_sync_audio" in cmd[0]:
            video = Path(cmd[1])
            (video.parent / f"{video.stem}_synced.flac").write_bytes(b"\x00")
        elif "02_extract" in cmd[0]:
            frames_dir = Path(cmd[2])
            frames_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, 5):
                (frames_dir / f"{i:06d}.png").write_bytes(b"\x00")
        elif "03_upscale" in cmd[0]:
            up_dir = Path(cmd[2])
            up_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, 5):
                (up_dir / f"{i:06d}.png").write_bytes(b"\x00")
                await asyncio.sleep(0.03)
        elif "04_mux" in cmd[0]:
            output = Path(cmd[3])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"\x00" * 1024)
        return 0

    monkeypatch.setattr(jobs_module, "run_stage", fake_run_stage)

    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")

    events = []
    sub = await mgr.subscribe(job_id)

    async def collect():
        async for e in sub:
            events.append(e)

    collector = asyncio.create_task(collect())
    await mgr.run_full_job(job_id, output_dir=tmp_path / "out", thumb_every_n=10_000)
    await asyncio.sleep(0.05)
    collector.cancel()

    progress = [e for e in events if isinstance(e, ProgressEvent)]
    thumbnails = [e for e in events if isinstance(e, ThumbnailEvent)]

    assert any(e.stage == "upscale" and e.current < e.total for e in progress)
    assert thumbnails == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
web/.venv/bin/pytest web/tests/test_jobs_orchestration.py::test_run_full_job_emits_progress_even_when_thumbnails_are_sparse -v
```

Expected: FAIL because `run_full_job()` still ties `upscale` progress updates to the thumbnail callback.

- [ ] **Step 3: Wire the new watcher into `run_full_job()`**

Update the extract and upscale sections inside `web/jobs.py`:

```python
frame_count = sum(1 for _ in frames_dir.glob("*.png"))
self.set_progress(job_id, "extract", frame_count, frame_count)
await self.publish(
    job_id,
    ProgressEvent(stage="extract", current=frame_count, total=frame_count),
)
await _stage_done(JobState.EXTRACTING, {"frame_count": frame_count})
```

First, change the `run_full_job()` signature so automatic thumbnail sampling is explicit:

```python
async def run_full_job(
    self,
    job_id: str,
    output_dir: Path,
    thumb_every_n: int | None = None,
    on_thumbnail: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
```

Then in the upscale section, derive a larger thumbnail stride and start a second watcher:

```python
thumb_stride = _thumbnail_stride(frame_count) if thumb_every_n is None else thumb_every_n
progress_watcher = asyncio.create_task(
    watch_upscale_progress(
        self,
        job_id,
        upscaled_dir,
        frame_count,
        stop,
        poll_interval=0.5,
    )
)
thumbnail_watcher = asyncio.create_task(
    watch_upscale_dir(upscaled_dir, thumb_stride, _on_frame, stop, poll_interval=1.0)
)
```

Replace the old single-watcher cleanup with:

```python
try:
    rc = await self._run_tracked(job_id, run)
finally:
    stop.set()
    await progress_watcher
    await thumbnail_watcher
```

And remove the progress update from `_on_frame()` so thumbnail emission no longer controls percentage updates:

```python
async def _on_frame(frame_id: str) -> None:
    src = upscaled_dir / f"{frame_id}.png"
    if not src.is_file():
        return
    dst = workdir / "thumbs" / f"up_{frame_id}.jpg"
    try:
        await thumbgen.generate(src, dst)
    except Exception:
        return
    await self.publish(
        job_id,
        ThumbnailEvent(
            frame_id=frame_id,
            kind="up",
            url=f"/api/jobs/{job_id}/frames/up/{frame_id}",
        ),
    )
```

- [ ] **Step 4: Run the orchestration regression test again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_jobs_orchestration.py::test_run_full_job_emits_progress_even_when_thumbnails_are_sparse -v
```

Expected: PASS

### Task 4: Regression verification

**Files:**
- Modify: none
- Test: `web/tests`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
web/.venv/bin/pytest \
  web/tests/test_server_basic.py \
  web/tests/test_jobs_progress.py \
  web/tests/test_jobs_orchestration.py -v
```

Expected: PASS

- [ ] **Step 2: Run the full web suite**

Run:

```bash
web/.venv/bin/pytest web/tests -q
```

Expected: PASS (with the existing environment-dependent skips unchanged)

- [ ] **Step 3: Manually verify the live UI**

Run:

```bash
./web/run_server.sh
```

Start a real job from the browser and verify:

- the panel changes from `Starting…` to `Downloading...` immediately
- it later shows `Extracting X / Y (Z%)`
- it later shows `Upscaling X / Y (Z%)`
- the thumbnail strip only updates occasionally rather than spamming every frame
