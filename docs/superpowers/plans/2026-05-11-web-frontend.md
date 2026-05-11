# Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin local web UI under `web/` that drives the existing pipeline scripts as subprocesses — paste-URL → probe → optional 5-frame preview → full run with live thumbnails → download.

**Architecture:** FastAPI + uvicorn server, vanilla HTML/JS/CSS frontend, Server-Sent Events for progress. Server shells out to the unchanged `00_sanitize.sh` … `04_mux.sh` (and Windows `*.ps1` mirrors) one stage at a time. Single in-process job, one job at a time globally. Localhost only (`127.0.0.1:8765`).

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, python-multipart, Pillow (with ffmpeg fallback), pytest. No frontend build step.

**Spec:** `docs/superpowers/specs/2026-05-11-web-frontend-design.md`

---

## File Structure

```
web/
  __init__.py
  server.py
  jobs.py
  state.py
  workdir.py
  probe.py
  models.py
  platform_info.py
  subprocess_runner.py
  events.py
  thumbnails.py
  live_watcher.py
  static/
    index.html
    app.js
    style.css
  tests/
    __init__.py
    conftest.py
    fixtures/
      ytdlp_dump.json
      ytdlp_age_gated.json
      tiny.mkv               # synthesized at first test run, .gitignored
    test_skeleton.py
    test_recommend.py
    test_models.py
    test_platform_info.py
    test_probe.py
    test_state.py
    test_events.py
    test_workdir.py
    test_subprocess_runner.py
    test_thumbnails.py
    test_server_basic.py
    test_server_jobs.py
    test_server_events.py
    test_pipeline_smoke.py
    manual_smoke.md
  requirements.txt
  requirements-dev.txt
  run_server.sh
  run_server.ps1
  README.md
```

Modifications:
- `install-dependencies.sh` — add `--with-web` flag.
- `windows/install-dependencies.ps1` — add `-WithWeb` switch.
- `.gitignore` — ignore `web/.venv/`, `web/tests/fixtures/tiny.mkv`, `web/__pycache__`, etc.

Existing pipeline scripts (`00_*.sh` … `04_*.sh`, `windows/*.ps1`) are **not modified**.

---

## Task 1: Project skeleton + dependencies

**Files:**
- Create: `web/__init__.py`
- Create: `web/requirements.txt`
- Create: `web/requirements-dev.txt`
- Create: `web/tests/__init__.py`
- Create: `web/tests/conftest.py`
- Create: `web/tests/test_skeleton.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p web/static web/tests/fixtures
touch web/__init__.py web/tests/__init__.py
```

Write `web/__init__.py`:

```python
"""Local web UI for the music-video upscaler pipeline."""

__version__ = "0.1.0"
```

Write `web/requirements.txt`:

```
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
pillow>=10.0
```

Write `web/requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27
```

Write `web/tests/conftest.py`:

```python
"""Shared pytest fixtures for the web package."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

Write `web/tests/test_skeleton.py`:

```python
"""Smoke test: the package imports and exposes a version."""
import web


def test_version_exposed():
    assert isinstance(web.__version__, str)
    assert web.__version__
```

Append to `.gitignore`:

```
# Web frontend
web/.venv/
web/__pycache__/
web/**/__pycache__/
web/.pytest_cache/
web/tests/fixtures/tiny.mkv
```

- [ ] **Step 2: Create venv and install dev deps**

```bash
python3 -m venv web/.venv
web/.venv/bin/pip install --upgrade pip
web/.venv/bin/pip install -r web/requirements-dev.txt
```

Expected: clean install, no errors.

- [ ] **Step 3: Run the smoke test**

```bash
web/.venv/bin/pytest web/tests/test_skeleton.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit**

```bash
git add web/__init__.py web/requirements.txt web/requirements-dev.txt \
        web/tests/__init__.py web/tests/conftest.py web/tests/test_skeleton.py \
        .gitignore
git commit -m "web: package skeleton + dev requirements"
```

---

## Task 2: Recommended scale (pure function)

**Files:**
- Create: `web/probe.py` (start of module — full content arrives in Task 5; for now only `recommended_scale`)
- Create: `web/tests/test_recommend.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_recommend.py`:

```python
import pytest

from web.probe import recommended_scale


@pytest.mark.parametrize(
    "height,expected",
    [
        (240, 4),
        (360, 4),
        (480, 4),
        (720, 4),
        (1079, 4),
        (1080, 2),
        (1440, 2),
        (2160, 2),
    ],
)
def test_recommended_scale(height, expected):
    assert recommended_scale(height) == expected


def test_recommended_scale_zero_or_negative_returns_4():
    assert recommended_scale(0) == 4
    assert recommended_scale(-1) == 4
```

- [ ] **Step 2: Run the test, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_recommend.py -v
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'web.probe'`.

- [ ] **Step 3: Implement**

`web/probe.py` (initial contents — extended in Task 5):

```python
"""yt-dlp probe + scale recommendation."""
from __future__ import annotations


def recommended_scale(height: int) -> int:
    """Return 2 for 1080p+, 4 for everything below (or unknown)."""
    if height >= 1080:
        return 2
    return 4
```

- [ ] **Step 4: Run the test, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_recommend.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/probe.py web/tests/test_recommend.py
git commit -m "web: recommended_scale() pure function"
```

---

## Task 3: Models discovery

**Files:**
- Create: `web/models.py`
- Create: `web/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_models.py`:

```python
from pathlib import Path

from web.models import ModelInfo, list_models, DEFAULT_MODEL


def _touch_pair(dir_: Path, name: str) -> None:
    (dir_ / f"{name}.param").write_text("")
    (dir_ / f"{name}.bin").write_bytes(b"")


def test_list_models_returns_only_complete_pairs(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")
    (tmp_path / "orphan.param").write_text("")  # missing .bin

    models = list_models(tmp_path)
    names = {m.name for m in models}

    assert names == {"realesr-general-x4v3", "realesrgan-x4plus"}


def test_list_models_marks_default(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")

    models = list_models(tmp_path)
    defaults = [m for m in models if m.default]

    assert len(defaults) == 1
    assert defaults[0].name == DEFAULT_MODEL


def test_list_models_returns_empty_for_empty_dir(tmp_path):
    assert list_models(tmp_path) == []


def test_list_models_returns_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert list_models(missing) == []


def test_list_models_attaches_known_hints(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesr-general-wdn-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")
    _touch_pair(tmp_path, "weird-custom-model")

    models = {m.name: m for m in list_models(tmp_path)}

    assert "compressed YouTube" in models["realesr-general-x4v3"].hint
    assert "denoise" in models["realesr-general-wdn-x4v3"].hint.lower()
    assert "clean" in models["realesrgan-x4plus"].hint.lower()
    assert models["weird-custom-model"].hint == ""


def test_modelinfo_is_a_dataclass():
    m = ModelInfo(name="x", default=False, hint="y")
    assert m.name == "x"
    assert m.default is False
    assert m.hint == "y"
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_models.py -v
```

Expected: ModuleNotFoundError for `web.models`.

- [ ] **Step 3: Implement**

`web/models.py`:

```python
"""Discover Real-ESRGAN ncnn model files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

DEFAULT_MODEL = "realesr-general-x4v3"

_HINTS = {
    "realesr-general-x4v3":
        "Recommended for compressed YouTube sources (default).",
    "realesr-general-wdn-x4v3":
        "Stronger denoise; use for very noisy or heavily compressed sources.",
    "realesrgan-x4plus":
        "Sharpest output, best for genuinely clean sources.",
    "realesrgan-x4plus-anime":
        "Anime/illustration content.",
    "realesr-animevideov3":
        "Anime video, lower resource cost.",
    "realesrnet-x4plus":
        "More conservative variant of x4plus, fewer hallucinations.",
}


@dataclass(frozen=True)
class ModelInfo:
    name: str
    default: bool
    hint: str


def list_models(models_dir: Path) -> List[ModelInfo]:
    """Return all complete .param/.bin pairs in models_dir.

    Marks the default model if present. Hints attached for known names.
    Returns an empty list if the directory does not exist.
    """
    if not models_dir.is_dir():
        return []

    pairs: List[str] = []
    for param in sorted(models_dir.glob("*.param")):
        stem = param.stem
        if (models_dir / f"{stem}.bin").is_file():
            pairs.append(stem)

    return [
        ModelInfo(name=name, default=(name == DEFAULT_MODEL), hint=_HINTS.get(name, ""))
        for name in pairs
    ]
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_models.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/models.py web/tests/test_models.py
git commit -m "web: model discovery with hints + default flag"
```

---

## Task 4: Platform info + stage script paths

**Files:**
- Create: `web/platform_info.py`
- Create: `web/tests/test_platform_info.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_platform_info.py`:

```python
from pathlib import Path

import pytest

from web import platform_info as pi


def test_repo_root_resolves_to_workspace_root():
    # repo root is the directory containing run_pipeline.sh
    assert (pi.REPO_ROOT / "run_pipeline.sh").is_file()
    assert (pi.REPO_ROOT / "windows" / "run_pipeline.ps1").is_file()


def test_stage_script_returns_known_stages_for_posix(monkeypatch):
    monkeypatch.setattr(pi, "is_windows", lambda: False)
    for stage in ["sanitize", "sync_audio", "extract", "upscale", "mux"]:
        path = pi.stage_script(stage)
        assert path.suffix == ".sh"
        assert path.name.startswith(("00_", "01_", "02_", "03_", "04_"))


def test_stage_script_returns_known_stages_for_windows(monkeypatch):
    monkeypatch.setattr(pi, "is_windows", lambda: True)
    for stage in ["sanitize", "sync_audio", "extract", "upscale", "mux"]:
        path = pi.stage_script(stage)
        assert path.suffix == ".ps1"
        assert "windows" in path.parts


def test_stage_script_unknown_raises():
    with pytest.raises(KeyError):
        pi.stage_script("frobnicate")


def test_stage_command_posix_includes_script_and_args(monkeypatch):
    monkeypatch.setattr(pi, "is_windows", lambda: False)
    cmd = pi.stage_command("extract", ["video.mkv", "frames/"])
    assert cmd[0].endswith("02_extract.sh")
    assert cmd[1:] == ["video.mkv", "frames/"]


def test_stage_command_windows_wraps_in_powershell(monkeypatch):
    monkeypatch.setattr(pi, "is_windows", lambda: True)
    cmd = pi.stage_command("extract", ["video.mkv", "frames/"])
    assert cmd[0] == "powershell"
    assert "-File" in cmd
    assert any(part.endswith("02_extract.ps1") for part in cmd)
    assert cmd[-2:] == ["video.mkv", "frames/"]
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_platform_info.py -v
```

Expected: ModuleNotFoundError for `web.platform_info`.

- [ ] **Step 3: Implement**

`web/platform_info.py`:

```python
"""OS detection + stage-script path resolution.

Module is named ``platform_info`` to avoid shadowing the stdlib ``platform``.
"""
from __future__ import annotations

import platform as _stdlib_platform
from pathlib import Path
from typing import Dict, List

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


def is_windows() -> bool:
    return _stdlib_platform.system() == "Windows"


_STAGE_SCRIPTS_POSIX: Dict[str, Path] = {
    "sanitize":   REPO_ROOT / "00_sanitize.sh",
    "sync_audio": REPO_ROOT / "01_sync_audio.sh",
    "extract":    REPO_ROOT / "02_extract.sh",
    "upscale":    REPO_ROOT / "03_upscale.sh",
    "mux":        REPO_ROOT / "04_mux.sh",
}

_STAGE_SCRIPTS_WINDOWS: Dict[str, Path] = {
    "sanitize":   REPO_ROOT / "windows" / "00_sanitize.ps1",
    "sync_audio": REPO_ROOT / "windows" / "01_sync_audio.ps1",
    "extract":    REPO_ROOT / "windows" / "02_extract.ps1",
    "upscale":    REPO_ROOT / "windows" / "03_upscale.ps1",
    "mux":        REPO_ROOT / "windows" / "04_mux.ps1",
}


def stage_script(stage: str) -> Path:
    table = _STAGE_SCRIPTS_WINDOWS if is_windows() else _STAGE_SCRIPTS_POSIX
    return table[stage]


def stage_command(stage: str, args: List[str]) -> List[str]:
    script = stage_script(stage)
    if is_windows():
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            *args,
        ]
    return [str(script), *args]
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_platform_info.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/platform_info.py web/tests/test_platform_info.py
git commit -m "web: platform detection + stage script command builder"
```

---

## Task 5: Probe wrapper (yt-dlp --dump-json parsing)

**Files:**
- Modify: `web/probe.py`
- Create: `web/tests/fixtures/ytdlp_dump.json`
- Create: `web/tests/fixtures/ytdlp_age_gated.json`
- Create: `web/tests/test_probe.py`

- [ ] **Step 1: Add fixtures**

`web/tests/fixtures/ytdlp_dump.json` (minimal happy-path):

```json
{
  "id": "abcdef",
  "title": "Some Music Video",
  "duration": 252.0,
  "width": 854,
  "height": 480,
  "fps": 23.976,
  "ext": "mp4"
}
```

`web/tests/fixtures/ytdlp_age_gated.json`:

```json
{
  "_error": true,
  "message": "Sign in to confirm your age. This video may be inappropriate for some users."
}
```

- [ ] **Step 2: Write the failing test**

`web/tests/test_probe.py`:

```python
import json
import subprocess
from pathlib import Path

import pytest

from web.probe import ProbeError, ProbeResult, parse_ytdlp_dump, probe

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ytdlp_dump_happy_path():
    payload = json.loads((FIXTURES / "ytdlp_dump.json").read_text())
    result = parse_ytdlp_dump(payload)
    assert result.title == "Some Music Video"
    assert result.duration == pytest.approx(252.0)
    assert result.width == 854
    assert result.height == 480
    assert result.fps == pytest.approx(23.976)
    assert result.recommended_scale == 4


def test_parse_ytdlp_dump_recommends_2x_for_1080p():
    payload = {"title": "X", "duration": 1, "width": 1920, "height": 1080, "fps": 30}
    assert parse_ytdlp_dump(payload).recommended_scale == 2


def test_parse_ytdlp_dump_handles_missing_fps():
    payload = {"title": "X", "duration": 1, "width": 640, "height": 360}
    result = parse_ytdlp_dump(payload)
    assert result.fps == 0.0


def test_parse_ytdlp_dump_raises_on_missing_required_fields():
    with pytest.raises(ProbeError):
        parse_ytdlp_dump({"title": "X"})  # missing height/width/duration


def test_probe_invokes_ytdlp_dump_json(monkeypatch):
    captured = {}

    class _R:
        returncode = 0
        stdout = (FIXTURES / "ytdlp_dump.json").read_text()
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = probe("https://www.youtube.com/watch?v=abc")
    assert "yt-dlp" in captured["cmd"][0] or captured["cmd"][0] == "yt-dlp"
    assert "--dump-json" in captured["cmd"]
    assert result.title == "Some Music Video"


def test_probe_raises_probeerror_on_ytdlp_failure(monkeypatch):
    class _R:
        returncode = 1
        stdout = ""
        stderr = "ERROR: Video unavailable"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _R())

    with pytest.raises(ProbeError) as excinfo:
        probe("https://www.youtube.com/watch?v=dead")
    assert "Video unavailable" in str(excinfo.value)
```

- [ ] **Step 3: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_probe.py -v
```

Expected: ImportError for `ProbeError`, `ProbeResult`, `parse_ytdlp_dump`, `probe`.

- [ ] **Step 4: Implement**

Replace `web/probe.py` with:

```python
"""yt-dlp probe + scale recommendation."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict


def recommended_scale(height: int) -> int:
    """Return 2 for 1080p+, 4 for everything below (or unknown)."""
    if height >= 1080:
        return 2
    return 4


@dataclass(frozen=True)
class ProbeResult:
    title: str
    duration: float
    width: int
    height: int
    fps: float
    recommended_scale: int


class ProbeError(RuntimeError):
    """yt-dlp could not return usable metadata for the URL."""


def _resolve_ytdlp() -> str:
    found = shutil.which("yt-dlp")
    return found if found else "yt-dlp"


def parse_ytdlp_dump(payload: Dict[str, Any]) -> ProbeResult:
    try:
        title = str(payload["title"])
        duration = float(payload["duration"])
        width = int(payload["width"])
        height = int(payload["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError(f"yt-dlp payload missing required fields: {exc}") from exc

    fps_raw = payload.get("fps")
    fps = float(fps_raw) if fps_raw is not None else 0.0

    return ProbeResult(
        title=title,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        recommended_scale=recommended_scale(height),
    )


def probe(url: str, timeout: float = 30.0) -> ProbeResult:
    cmd = [_resolve_ytdlp(), "--dump-json", "--no-warnings", url]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        raise ProbeError(msg)
    try:
        payload = json.loads(proc.stdout.splitlines()[0])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ProbeError(f"yt-dlp returned non-JSON output: {exc}") from exc
    return parse_ytdlp_dump(payload)
```

- [ ] **Step 5: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_probe.py web/tests/test_recommend.py -v
```

Expected: `15 passed` (9 from recommend + 6 from probe).

- [ ] **Step 6: Commit**

```bash
git add web/probe.py web/tests/test_probe.py web/tests/fixtures/
git commit -m "web: yt-dlp probe wrapper with parse + run path"
```

---

## Task 6: Job state machine

**Files:**
- Create: `web/state.py`
- Create: `web/tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_state.py`:

```python
import pytest

from web.state import IllegalTransition, JobKind, JobState, can_transition


def test_jobstate_has_expected_members():
    expected = {
        "CREATED", "DOWNLOADING", "PREPARING", "EXTRACTING",
        "UPSCALING", "MUXING", "COMPLETE", "FAILED", "CANCELLED",
    }
    assert {s.name for s in JobState} == expected


def test_jobkind_has_full_and_preview():
    assert {k.name for k in JobKind} == {"FULL", "PREVIEW"}


def test_terminal_states_are_terminal():
    for s in [JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED]:
        assert s.is_terminal()


def test_active_states_are_not_terminal():
    for s in [JobState.CREATED, JobState.DOWNLOADING, JobState.PREPARING,
              JobState.EXTRACTING, JobState.UPSCALING, JobState.MUXING]:
        assert not s.is_terminal()


def test_can_transition_full_pipeline():
    chain = [
        JobState.CREATED, JobState.DOWNLOADING, JobState.PREPARING,
        JobState.EXTRACTING, JobState.UPSCALING, JobState.MUXING,
        JobState.COMPLETE,
    ]
    for src, dst in zip(chain, chain[1:]):
        assert can_transition(src, dst), f"{src} -> {dst} should be allowed"


def test_can_transition_to_failed_or_cancelled_from_any_active_state():
    for src in [JobState.DOWNLOADING, JobState.PREPARING, JobState.EXTRACTING,
                JobState.UPSCALING, JobState.MUXING]:
        assert can_transition(src, JobState.FAILED)
        assert can_transition(src, JobState.CANCELLED)


def test_cannot_transition_from_terminal_state():
    for src in [JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED]:
        for dst in JobState:
            assert not can_transition(src, dst)


def test_cannot_skip_active_states():
    assert not can_transition(JobState.DOWNLOADING, JobState.UPSCALING)
    assert not can_transition(JobState.CREATED, JobState.MUXING)


def test_illegal_transition_is_an_exception():
    err = IllegalTransition(JobState.COMPLETE, JobState.UPSCALING)
    assert "COMPLETE" in str(err) and "UPSCALING" in str(err)
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_state.py -v
```

Expected: ModuleNotFoundError for `web.state`.

- [ ] **Step 3: Implement**

`web/state.py`:

```python
"""Job state machine."""
from __future__ import annotations

from enum import Enum
from typing import Set


class JobState(str, Enum):
    CREATED = "created"
    DOWNLOADING = "downloading"
    PREPARING = "preparing"
    EXTRACTING = "extracting"
    UPSCALING = "upscaling"
    MUXING = "muxing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in _TERMINAL


class JobKind(str, Enum):
    FULL = "full"
    PREVIEW = "preview"


_TERMINAL: Set[JobState] = {JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED}

_FORWARD_CHAIN = [
    JobState.CREATED,
    JobState.DOWNLOADING,
    JobState.PREPARING,
    JobState.EXTRACTING,
    JobState.UPSCALING,
    JobState.MUXING,
    JobState.COMPLETE,
]
_FORWARD_INDEX = {s: i for i, s in enumerate(_FORWARD_CHAIN)}
_ACTIVE = set(_FORWARD_CHAIN[1:-1])  # DOWNLOADING..MUXING


def can_transition(src: JobState, dst: JobState) -> bool:
    if src.is_terminal():
        return False
    if dst in (JobState.FAILED, JobState.CANCELLED):
        return src in _ACTIVE or src == JobState.CREATED
    if src in _FORWARD_INDEX and dst in _FORWARD_INDEX:
        return _FORWARD_INDEX[dst] == _FORWARD_INDEX[src] + 1
    return False


class IllegalTransition(RuntimeError):
    def __init__(self, src: JobState, dst: JobState):
        super().__init__(f"Illegal job state transition: {src.name} -> {dst.name}")
        self.src = src
        self.dst = dst
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_state.py -v
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/state.py web/tests/test_state.py
git commit -m "web: JobState/JobKind enums + transition validator"
```

---

## Task 7: SSE event types

**Files:**
- Create: `web/events.py`
- Create: `web/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_events.py`:

```python
import json

from web.events import (
    CompleteEvent, ErrorEvent, LogEvent, ProgressEvent, StageEvent,
    ThumbnailEvent, sse_format,
)


def _decode_sse(blob: str) -> dict:
    assert blob.startswith("data: ")
    assert blob.endswith("\n\n")
    return json.loads(blob[len("data: "):-2])


def test_stage_event_serializes():
    out = _decode_sse(StageEvent(stage="upscale", status="started").to_sse())
    assert out == {"type": "stage", "stage": "upscale", "status": "started", "extra": {}}


def test_stage_event_carries_extra():
    out = _decode_sse(
        StageEvent(stage="extract", status="done", extra={"frame_count": 4500}).to_sse()
    )
    assert out["extra"] == {"frame_count": 4500}


def test_progress_event_serializes():
    out = _decode_sse(
        ProgressEvent(stage="upscale", current=1024, total=4500).to_sse()
    )
    assert out == {"type": "progress", "stage": "upscale", "current": 1024, "total": 4500}


def test_thumbnail_event_serializes():
    out = _decode_sse(
        ThumbnailEvent(frame_id="000123", kind="up", url="/api/jobs/x/frames/up/000123").to_sse()
    )
    assert out["type"] == "thumbnail"
    assert out["url"].endswith("000123")


def test_log_event_serializes():
    out = _decode_sse(LogEvent(line="hello").to_sse())
    assert out == {"type": "log", "line": "hello"}


def test_complete_event_serializes():
    out = _decode_sse(CompleteEvent(output="/tmp/x.mkv", size_bytes=42).to_sse())
    assert out == {"type": "complete", "output": "/tmp/x.mkv", "size_bytes": 42}


def test_error_event_serializes():
    out = _decode_sse(ErrorEvent(stage="upscale", message="boom").to_sse())
    assert out == {"type": "error", "stage": "upscale", "message": "boom"}


def test_sse_format_terminates_with_blank_line():
    blob = sse_format({"type": "ping"})
    assert blob == 'data: {"type": "ping"}\n\n'
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_events.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`web/events.py`:

```python
"""SSE event types and serialization."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def sse_format(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(', ', ': '))}\n\n"


@dataclass(frozen=True)
class StageEvent:
    stage: str
    status: str  # "started" | "done"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        return sse_format({
            "type": "stage",
            "stage": self.stage,
            "status": self.status,
            "extra": dict(self.extra),
        })


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    current: int
    total: int

    def to_sse(self) -> str:
        return sse_format({
            "type": "progress",
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
        })


@dataclass(frozen=True)
class ThumbnailEvent:
    frame_id: str
    kind: str  # "src" | "up"
    url: str

    def to_sse(self) -> str:
        return sse_format({
            "type": "thumbnail",
            "frame_id": self.frame_id,
            "kind": self.kind,
            "url": self.url,
        })


@dataclass(frozen=True)
class LogEvent:
    line: str

    def to_sse(self) -> str:
        return sse_format({"type": "log", "line": self.line})


@dataclass(frozen=True)
class CompleteEvent:
    output: str
    size_bytes: int

    def to_sse(self) -> str:
        return sse_format({
            "type": "complete",
            "output": self.output,
            "size_bytes": self.size_bytes,
        })


@dataclass(frozen=True)
class ErrorEvent:
    stage: Optional[str]
    message: str

    def to_sse(self) -> str:
        return sse_format({
            "type": "error",
            "stage": self.stage,
            "message": self.message,
        })
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_events.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/events.py web/tests/test_events.py
git commit -m "web: SSE event dataclasses + sse_format"
```

---

## Task 8: Workdir manager

**Files:**
- Create: `web/workdir.py`
- Create: `web/tests/test_workdir.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_workdir.py`:

```python
import re
import time
from pathlib import Path

import pytest

from web.workdir import WorkdirManager, default_root, default_output_dir


def test_default_root_is_under_user_cache():
    p = default_root()
    assert "music-video-upscaler" in p.parts
    assert p.name == "jobs"


def test_default_output_dir_returns_existing_kind_per_os():
    p = default_output_dir()
    assert p.name == "MusicVideoUpscaled"


def test_create_job_returns_id_and_dir(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert re.match(r"^\d{8}-\d{6}-[a-z0-9]{6}$", job_id)
    assert workdir.is_dir()
    assert workdir.parent == tmp_path
    assert (workdir / "source").is_dir()
    assert (workdir / "thumbs").is_dir()
    assert (workdir / "output").is_dir()


def test_state_path_returns_state_json(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert mgr.state_path(job_id) == workdir / "state.json"


def test_log_path_returns_log_txt(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert mgr.log_path(job_id) == workdir / "log.txt"


def test_get_workdir_raises_when_missing(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.get_workdir("does-not-exist")


def test_cleanup_keeps_recent_n_and_non_terminal(tmp_path):
    import json

    mgr = WorkdirManager(root=tmp_path, keep_recent=2, max_age_seconds=1)
    ids = []
    for _ in range(5):
        jid, wd = mgr.create_job()
        # Mark as complete (terminal)
        (wd / "state.json").write_text(json.dumps({"state": "complete"}))
        ids.append(jid)
        time.sleep(0.01)
    # Bend mtime backwards on three oldest to trigger cleanup
    for jid in ids[:3]:
        wd = mgr.get_workdir(jid)
        old = time.time() - 10
        for p in wd.rglob("*"):
            try:
                import os
                os.utime(p, (old, old))
            except OSError:
                pass
        import os
        os.utime(wd, (old, old))

    mgr.cleanup()

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert ids[-1] in remaining
    assert ids[-2] in remaining
    assert ids[0] not in remaining


def test_cleanup_keeps_non_terminal_even_when_old(tmp_path):
    import json
    import os

    mgr = WorkdirManager(root=tmp_path, keep_recent=0, max_age_seconds=1)
    jid, wd = mgr.create_job()
    (wd / "state.json").write_text(json.dumps({"state": "upscaling"}))
    old = time.time() - 100
    os.utime(wd, (old, old))

    mgr.cleanup()
    assert wd.is_dir()
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_workdir.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`web/workdir.py`:

```python
"""Per-job workdir lifecycle: create, locate, clean."""
from __future__ import annotations

import json
import os
import platform as _stdlib_platform
import secrets
import shutil
import string
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def default_root() -> Path:
    if _stdlib_platform.system() == "Windows":
        cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif _stdlib_platform.system() == "Darwin":
        cache = Path.home() / "Library" / "Caches"
    else:
        cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache / "music-video-upscaler" / "jobs"


def default_output_dir() -> Path:
    home = Path.home()
    if _stdlib_platform.system() == "Darwin":
        return home / "Movies" / "MusicVideoUpscaled"
    if _stdlib_platform.system() == "Windows":
        return home / "Videos" / "MusicVideoUpscaled"
    return home / "Videos" / "MusicVideoUpscaled"


_TERMINAL = {"complete", "failed", "cancelled"}
_ALPHABET = string.ascii_lowercase + string.digits


def _new_job_id() -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"{ts}-{suffix}"


class WorkdirManager:
    def __init__(
        self,
        root: Optional[Path] = None,
        keep_recent: int = 5,
        max_age_seconds: float = 7 * 24 * 3600,
    ) -> None:
        self.root = (root or default_root()).resolve()
        self.keep_recent = keep_recent
        self.max_age_seconds = max_age_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job(self) -> Tuple[str, Path]:
        for _ in range(8):
            job_id = _new_job_id()
            workdir = self.root / job_id
            try:
                workdir.mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                time.sleep(0.01)
                continue
        else:
            raise RuntimeError("could not allocate a fresh job id")
        for sub in ("source", "thumbs", "output"):
            (workdir / sub).mkdir(parents=True, exist_ok=True)
        return job_id, workdir

    def get_workdir(self, job_id: str) -> Path:
        wd = self.root / job_id
        if not wd.is_dir():
            raise FileNotFoundError(f"workdir not found: {job_id}")
        return wd

    def state_path(self, job_id: str) -> Path:
        return self.get_workdir(job_id) / "state.json"

    def log_path(self, job_id: str) -> Path:
        return self.get_workdir(job_id) / "log.txt"

    def cleanup(self) -> None:
        now = time.time()
        candidates = [p for p in self.root.iterdir() if p.is_dir()]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        recent = set(candidates[: self.keep_recent])
        for wd in candidates:
            if wd in recent:
                continue
            age = now - wd.stat().st_mtime
            if age <= self.max_age_seconds:
                continue
            state = "unknown"
            sp = wd / "state.json"
            if sp.is_file():
                try:
                    state = json.loads(sp.read_text()).get("state", "unknown")
                except (json.JSONDecodeError, OSError):
                    state = "unknown"
            if state not in _TERMINAL and state != "unknown":
                continue
            try:
                shutil.rmtree(wd)
            except OSError:
                pass
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_workdir.py -v
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/workdir.py web/tests/test_workdir.py
git commit -m "web: WorkdirManager (create/locate/cleanup) + OS defaults"
```

---

## Task 9: Subprocess runner

**Files:**
- Create: `web/subprocess_runner.py`
- Create: `web/tests/test_subprocess_runner.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_subprocess_runner.py`:

```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_subprocess_runner.py -v
```

Expected: ImportError.

Add to `web/tests/conftest.py` so pytest-asyncio uses auto mode:

```python
# Append:
import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if asyncio_test := item.get_closest_marker("asyncio"):
            continue


# Configure pytest-asyncio
import pytest_asyncio  # noqa: E402,F401
```

Better — add a `pytest.ini` style in `web/pyproject.toml` or simpler: `web/tests/conftest.py` just sets `asyncio_mode = "auto"` is via pytest config. Use `pytest.ini` instead to keep things explicit.

Create `web/pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
```

Re-run; the test should now hit the import error properly.

- [ ] **Step 3: Implement**

`web/subprocess_runner.py`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_subprocess_runner.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/subprocess_runner.py web/tests/test_subprocess_runner.py web/pytest.ini
git commit -m "web: async subprocess runner with proc-group cancel"
```

---

## Task 10: Thumbnail generation

**Files:**
- Create: `web/thumbnails.py`
- Create: `web/tests/test_thumbnails.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_thumbnails.py`:

```python
from pathlib import Path

import pytest

from web.thumbnails import ThumbnailGenerator


def _make_png(path: Path, width: int = 1920, height: int = 1080) -> None:
    from PIL import Image
    Image.new("RGB", (width, height), (10, 20, 30)).save(path, "PNG")


@pytest.mark.asyncio
async def test_generate_with_pillow_produces_360px_jpeg(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator()
    await gen.generate(src, dst, width=360)

    from PIL import Image
    with Image.open(dst) as im:
        assert im.format == "JPEG"
        assert im.size[0] == 360
        assert im.size[1] == 202  # 1080 * (360/1920)


@pytest.mark.asyncio
async def test_generate_idempotent_when_dst_exists(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator()
    await gen.generate(src, dst)
    mtime1 = dst.stat().st_mtime
    await gen.generate(src, dst)
    assert dst.stat().st_mtime == mtime1


@pytest.mark.asyncio
async def test_ffmpeg_fallback_when_pillow_disabled(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator(prefer_pillow=False)
    await gen.generate(src, dst, width=360)
    assert dst.is_file()
    assert dst.stat().st_size > 0
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_thumbnails.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`web/thumbnails.py`:

```python
"""360px thumbnail generation: Pillow primary, ffmpeg fallback."""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False


@dataclass
class ThumbnailGenerator:
    prefer_pillow: bool = True
    quality: int = 80

    async def generate(self, src: Path, dst: Path, width: int = 360) -> None:
        if dst.is_file() and dst.stat().st_size > 0:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if self.prefer_pillow and _HAS_PILLOW:
            await asyncio.to_thread(self._generate_pillow, src, dst, width)
        else:
            await self._generate_ffmpeg(src, dst, width)

    def _generate_pillow(self, src: Path, dst: Path, width: int) -> None:
        with Image.open(src) as im:
            im = im.convert("RGB")
            ratio = width / im.size[0]
            new_size = (width, max(1, int(round(im.size[1] * ratio))))
            im = im.resize(new_size, Image.LANCZOS)
            im.save(dst, "JPEG", quality=self.quality, optimize=True)

    async def _generate_ffmpeg(self, src: Path, dst: Path, width: int) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner", "-nostdin", "-y",
            "-i", str(src),
            "-vf", f"scale={width}:-1",
            "-q:v", "5",
            str(dst),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0 or not dst.is_file():
            raise RuntimeError(f"ffmpeg thumbnail generation failed for {src}")
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_thumbnails.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/thumbnails.py web/tests/test_thumbnails.py
git commit -m "web: ThumbnailGenerator (Pillow + ffmpeg fallback)"
```

---

## Task 11: Live thumbnail watcher

**Files:**
- Create: `web/live_watcher.py`
- Add tests inline in `web/tests/test_thumbnails.py` (or new file)

- [ ] **Step 1: Write the failing test**

Create `web/tests/test_live_watcher.py`:

```python
import asyncio
from pathlib import Path

import pytest

from web.live_watcher import watch_upscale_dir


@pytest.mark.asyncio
async def test_watcher_emits_every_n_frames(tmp_path):
    seen = []

    async def on_frame(frame_id: str) -> None:
        seen.append(frame_id)

    stop = asyncio.Event()

    async def producer():
        for i in range(1, 11):
            (tmp_path / f"{i:06d}.png").write_bytes(b"x")
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        stop.set()

    watcher = asyncio.create_task(
        watch_upscale_dir(tmp_path, every_n=4, on_frame=on_frame, stop_event=stop, poll_interval=0.05)
    )
    await producer()
    await watcher

    # crossed 4 (000004) and 8 (000008)
    assert "000004" in seen
    assert "000008" in seen
    assert "000010" not in seen


@pytest.mark.asyncio
async def test_watcher_stops_on_event(tmp_path):
    stop = asyncio.Event()
    stop.set()
    seen = []

    async def on_frame(_: str) -> None:
        seen.append(_)

    await asyncio.wait_for(
        watch_upscale_dir(tmp_path, every_n=1, on_frame=on_frame, stop_event=stop, poll_interval=0.01),
        timeout=1.0,
    )
    assert seen == []
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_live_watcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement**

`web/live_watcher.py`:

```python
"""Background watcher that emits 'thumbnail-worthy' frame ids while upscale runs."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Awaitable, Callable

FrameHandler = Callable[[str], Awaitable[None]]


async def watch_upscale_dir(
    upscale_dir: Path,
    every_n: int,
    on_frame: FrameHandler,
    stop_event: asyncio.Event,
    poll_interval: float = 1.0,
) -> None:
    """Poll upscale_dir; for each new count crossing a multiple of every_n,
    invoke on_frame with that frame's zero-padded id (e.g. '000200')."""
    last_emitted = 0
    upscale_dir.mkdir(parents=True, exist_ok=True)

    while not stop_event.is_set():
        try:
            count = sum(1 for e in os.scandir(upscale_dir) if e.is_file() and e.name.endswith(".png"))
        except FileNotFoundError:
            count = 0

        threshold = (count // every_n) * every_n
        while last_emitted + every_n <= threshold:
            last_emitted += every_n
            frame_id = f"{last_emitted:06d}"
            try:
                await on_frame(frame_id)
            except Exception:
                pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_live_watcher.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/live_watcher.py web/tests/test_live_watcher.py
git commit -m "web: live watcher emits frame ids every N upscaled frames"
```

---

## Task 12: JobManager — job model + state.json + subscribers

**Files:**
- Create: `web/jobs.py` (initial: data model + subscribe/publish only — orchestration arrives in Task 13)
- Create: `web/tests/test_jobs_model.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_jobs_model.py`:

```python
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
    mgr.set_state(job_id, JobState.COMPLETE)
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
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_jobs_model.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`web/jobs.py`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_jobs_model.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/jobs.py web/tests/test_jobs_model.py
git commit -m "web: JobManager data model + pub/sub + persistence"
```

---

## Task 13: Job orchestration — full pipeline

**Files:**
- Modify: `web/jobs.py` — append `run_full_job(...)`
- Create: `web/tests/test_jobs_orchestration.py` (mocks subprocess_runner + ytdlp)

- [ ] **Step 1: Write the failing test**

`web/tests/test_jobs_orchestration.py`:

```python
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from web.events import CompleteEvent, ErrorEvent, StageEvent
from web.jobs import JobManager
from web.state import JobState


def _patch_stages(monkeypatch, *, fail_at: str = ""):
    """Patch run_stage so it just touches expected output and returns 0 (or 1 at fail_at)."""
    from web import jobs as jobs_module

    async def fake_run_stage(run):
        # Simulate the stage having succeeded by creating its expected output.
        cmd = run.cmd
        run.process = type("P", (), {"returncode": 0, "pid": 12345})()
        if "yt-dlp" in cmd[0] or cmd[0].endswith("yt-dlp"):
            (run.cwd / "video.mp4").write_bytes(b"\x00")
            (run.cwd / "audio.m4a").write_bytes(b"\x00")
            stage = "download"
        elif "01_sync_audio" in cmd[0]:
            video = Path(cmd[1])
            (video.parent / f"{video.stem}_synced.flac").write_bytes(b"\x00")
            stage = "sync_audio"
        elif "02_extract" in cmd[0]:
            frames_dir = Path(cmd[2])
            frames_dir.mkdir(parents=True, exist_ok=True)
            (frames_dir / "000001.png").write_bytes(b"\x00")
            stage = "extract"
        elif "03_upscale" in cmd[0]:
            up_dir = Path(cmd[2])
            up_dir.mkdir(parents=True, exist_ok=True)
            (up_dir / "000001.png").write_bytes(b"\x00")
            stage = "upscale"
        elif "04_mux" in cmd[0]:
            output = Path(cmd[3])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"\x00" * 1024)
            stage = "mux"
        elif "00_sanitize" in cmd[0]:
            stage = "sanitize"
        else:
            stage = "?"

        return 1 if stage == fail_at else 0

    monkeypatch.setattr(jobs_module, "run_stage", fake_run_stage)


@pytest.mark.asyncio
async def test_run_full_job_happy_path(tmp_path, monkeypatch):
    _patch_stages(monkeypatch)
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full", url="https://x.test/v", model="realesr-general-x4v3",
        scale=4, output_format="mkv",
    )
    out_dir = tmp_path / "out"
    await mgr.run_full_job(job_id, output_dir=out_dir)

    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.COMPLETE.value
    assert snap["output_path"]
    assert Path(snap["output_path"]).is_file()


@pytest.mark.asyncio
async def test_run_full_job_failure_marks_failed(tmp_path, monkeypatch):
    _patch_stages(monkeypatch, fail_at="upscale")
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="https://x.test/v", model="m",
        scale=4, output_format="mkv",
    )
    await mgr.run_full_job(job_id, output_dir=tmp_path / "out")

    snap = mgr.get_job(job_id)
    assert snap["state"] == JobState.FAILED.value
    assert "upscale" in (snap["error"] or "").lower()


@pytest.mark.asyncio
async def test_run_full_job_publishes_stage_events(tmp_path, monkeypatch):
    _patch_stages(monkeypatch)
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, _ = mgr.register_job(
        kind="full", url="u", model="m", scale=4, output_format="mkv",
    )

    events = []
    sub = await mgr.subscribe(job_id)

    async def collect():
        async for e in sub:
            events.append(e)

    collector = asyncio.create_task(collect())
    await mgr.run_full_job(job_id, output_dir=tmp_path / "out")
    await asyncio.sleep(0.05)
    collector.cancel()

    stages = [getattr(e, "stage", None) for e in events if isinstance(e, StageEvent)]
    assert "downloading" in stages
    assert "upscaling" in stages
    assert "muxing" in stages
    assert any(isinstance(e, CompleteEvent) for e in events)
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_jobs_orchestration.py -v
```

Expected: AttributeError on `JobManager.run_full_job` or import errors.

- [ ] **Step 3: Implement — extend `web/jobs.py`**

Append these imports near the top of `web/jobs.py` (alongside the existing ones):

```python
import shutil
import sys
from typing import Awaitable, Callable

from web.live_watcher import watch_upscale_dir
from web.platform_info import REPO_ROOT, stage_command
from web.subprocess_runner import StageRun, run_stage
from web.thumbnails import ThumbnailGenerator
```

Append the orchestration method to `JobManager`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_jobs_orchestration.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/jobs.py web/tests/test_jobs_orchestration.py
git commit -m "web: full pipeline orchestration with live thumbnails"
```

---

## Task 14: Preview job orchestration

**Files:**
- Modify: `web/jobs.py` — append `run_preview_job(...)`
- Create: `web/tests/test_jobs_preview.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_jobs_preview.py`:

```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_jobs_preview.py -v
```

Expected: AttributeError on `run_preview_job`.

- [ ] **Step 3: Implement — append to `web/jobs.py`**

```python
    async def run_preview_job(self, job_id: str) -> None:
        rec = self._records[job_id]
        workdir = self.workdir.get_workdir(job_id)
        log = self.workdir.log_path(job_id)
        source_dir = workdir / "source"
        frames_dir = workdir / "tmp_frames_preview"
        upscaled_dir = workdir / f"tmp_upscaled_preview_{rec.scale}x"

        async def _line(line: str) -> None:
            await self.publish(job_id, LogEvent(line=line))

        try:
            self.set_state(job_id, JobState.DOWNLOADING)
            await self.publish(job_id, StageEvent(stage="downloading", status="started"))
            ytdlp = shutil.which("yt-dlp") or "yt-dlp"
            dl_cmd = [
                ytdlp, "--no-warnings",
                "--download-sections", "*0-10",
                "-f", "bv*+ba/b", "--merge-output-format", "mp4",
                "-o", str(source_dir / "video.%(ext)s"),
                rec.url,
            ]
            rc = await run_stage(StageRun(cmd=dl_cmd, cwd=source_dir, log_path=log, on_line=_line))
            if rc != 0:
                raise RuntimeError("preview download failed")
            await self.publish(job_id, StageEvent(stage="downloading", status="done"))
            video_path = next(source_dir.glob("video.*"))

            self.set_state(job_id, JobState.EXTRACTING)
            ext_cmd = stage_command("extract", [str(video_path), str(frames_dir)])
            rc = await run_stage(StageRun(cmd=ext_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line))
            if rc != 0:
                raise RuntimeError("preview extract failed")
            all_frames = sorted(frames_dir.glob("*.png"))
            if not all_frames:
                raise RuntimeError("no frames extracted")

            # Pick 5 evenly spaced
            n = min(5, len(all_frames))
            picks = [all_frames[int(i * (len(all_frames) - 1) / max(n - 1, 1))] for i in range(n)]
            picks_dir = workdir / "tmp_frames_picks"
            picks_dir.mkdir(parents=True, exist_ok=True)
            for p in picks_dir.glob("*.png"):
                p.unlink()
            for p in picks:
                shutil.copy2(p, picks_dir / p.name)

            self.set_state(job_id, JobState.UPSCALING)
            up_cmd = stage_command(
                "upscale",
                [str(picks_dir), str(upscaled_dir), str(rec.scale), rec.model],
            )
            rc = await run_stage(StageRun(cmd=up_cmd, cwd=REPO_ROOT, log_path=log, on_line=_line))
            if rc != 0:
                raise RuntimeError("preview upscale failed")

            thumbgen = ThumbnailGenerator()
            for p in picks:
                src_thumb = workdir / "thumbs" / f"src_{p.stem}.jpg"
                await thumbgen.generate(p, src_thumb)
                up_src = upscaled_dir / p.name
                if up_src.is_file():
                    up_thumb = workdir / "thumbs" / f"up_{p.stem}.jpg"
                    await thumbgen.generate(up_src, up_thumb)
                    await self.publish(job_id, ThumbnailEvent(
                        frame_id=p.stem, kind="up",
                        url=f"/api/jobs/{job_id}/frames/up/{p.stem}",
                    ))
                await self.publish(job_id, ThumbnailEvent(
                    frame_id=p.stem, kind="src",
                    url=f"/api/jobs/{job_id}/frames/src/{p.stem}",
                ))

            self.set_state(job_id, JobState.MUXING)  # advance through chain
            self.set_state(job_id, JobState.COMPLETE)
            await self.publish(job_id, CompleteEvent(
                output=str(workdir / "thumbs"),
                size_bytes=0,
            ))

        except Exception as exc:
            self.set_error(job_id, str(exc))
            try:
                self.set_state(job_id, JobState.FAILED)
            except IllegalTransition:
                pass
            await self.publish(job_id, ErrorEvent(stage=rec.state, message=str(exc)))
        finally:
            await self.close_subscribers(job_id)
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_jobs_preview.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/jobs.py web/tests/test_jobs_preview.py
git commit -m "web: preview job orchestration (10s download, 5 sample frames)"
```

---

## Task 15: HTTP routes — health, models, probe

**Files:**
- Create: `web/server.py` (initial: app + first routes)
- Create: `web/tests/test_server_basic.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_server_basic.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.server import build_app


@pytest.fixture
def client(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")

    app = build_app(models_dir=models_dir, workdir_root=tmp_path / "jobs")
    return TestClient(app)


def test_health_returns_200(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert "missing" in body


def test_models_returns_default(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    models = r.json()
    assert any(m["default"] and m["name"] == "realesr-general-x4v3" for m in models)


def test_probe_validates_url(client):
    r = client.post("/api/probe", json={"url": ""})
    assert r.status_code == 422


def test_probe_returns_metadata(client, monkeypatch):
    from web import server as server_module
    from web.probe import ProbeResult

    def fake_probe(url, timeout=30.0):
        return ProbeResult(
            title="X", duration=10.0, width=854, height=480, fps=24.0, recommended_scale=4
        )

    monkeypatch.setattr(server_module, "probe", fake_probe)

    r = client.post("/api/probe", json={"url": "https://www.youtube.com/watch?v=x"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "X"
    assert body["recommended_scale"] == 4


def test_probe_returns_400_on_probe_error(client, monkeypatch):
    from web import server as server_module
    from web.probe import ProbeError

    def fake_probe(url, timeout=30.0):
        raise ProbeError("Video unavailable")

    monkeypatch.setattr(server_module, "probe", fake_probe)

    r = client.post("/api/probe", json={"url": "https://www.youtube.com/watch?v=dead"})
    assert r.status_code == 400
    assert "unavailable" in r.json()["detail"].lower()


def test_index_html_is_served(client):
    r = client.get("/")
    # The HTML doesn't exist yet at this task; route should return 404 or empty.
    assert r.status_code in (200, 404)
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py -v
```

Expected: ImportError on `build_app`.

- [ ] **Step 3: Implement**

`web/server.py`:

```python
"""FastAPI application factory and route handlers."""
from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.jobs import JobManager
from web.models import list_models
from web.platform_info import REPO_ROOT
from web.probe import ProbeError, probe

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_MODELS_DIR = REPO_ROOT / "models"


class ProbeRequest(BaseModel):
    url: str = Field(min_length=1)


def _check_health(models_dir: Path) -> dict:
    missing = []
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        if shutil.which(tool) is None:
            missing.append(tool)
    realesr_candidates = [
        REPO_ROOT / "tools" / "realesrgan-ncnn-vulkan",
        REPO_ROOT / "windows" / "realesrgan-ncnn-vulkan.exe",
    ]
    if not (
        shutil.which("realesrgan-ncnn-vulkan")
        or any(p.exists() for p in realesr_candidates)
    ):
        missing.append("realesrgan-ncnn-vulkan")
    if not list_models(models_dir):
        missing.append("models")
    return {"ok": not missing, "missing": missing}


def build_app(
    models_dir: Optional[Path] = None,
    workdir_root: Optional[Path] = None,
) -> FastAPI:
    app = FastAPI(title="music-video-upscaler", version="0.1.0")

    models_dir = (models_dir or DEFAULT_MODELS_DIR).resolve()
    job_manager = JobManager(workdir_root=workdir_root)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        index_html = STATIC_DIR / "index.html"
        if not index_html.is_file():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_html)

    @app.get("/api/health")
    def health():
        return _check_health(models_dir)

    @app.get("/api/models")
    def models():
        return [asdict(m) for m in list_models(models_dir)]

    @app.post("/api/probe")
    def probe_endpoint(req: ProbeRequest):
        try:
            result = probe(req.url)
        except ProbeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return asdict(result)

    app.state.job_manager = job_manager
    app.state.models_dir = models_dir
    return app


app = build_app()
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/server.py web/tests/test_server_basic.py
git commit -m "web: FastAPI app factory + health/models/probe endpoints"
```

---

## Task 16: HTTP routes — jobs (POST, GET, cancel)

**Files:**
- Modify: `web/server.py`
- Create: `web/tests/test_server_jobs.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_server_jobs.py`:

```python
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.server import build_app


@pytest.fixture
def client(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")
    app = build_app(models_dir=models_dir, workdir_root=tmp_path / "jobs")
    return TestClient(app)


def _patch_orchestration(monkeypatch):
    from web import jobs as jobs_module

    async def fake_full(self, job_id, output_dir, **_):
        from web.state import JobState
        self.set_state(job_id, JobState.DOWNLOADING)
        self.set_state(job_id, JobState.PREPARING)
        self.set_state(job_id, JobState.EXTRACTING)
        self.set_state(job_id, JobState.UPSCALING)
        self.set_state(job_id, JobState.MUXING)
        self.set_state(job_id, JobState.COMPLETE)
        self.set_output(job_id, output_dir / "x.mkv")

    async def fake_preview(self, job_id):
        from web.state import JobState
        self.set_state(job_id, JobState.DOWNLOADING)
        self.set_state(job_id, JobState.PREPARING)
        self.set_state(job_id, JobState.EXTRACTING)
        self.set_state(job_id, JobState.UPSCALING)
        self.set_state(job_id, JobState.MUXING)
        self.set_state(job_id, JobState.COMPLETE)

    monkeypatch.setattr(jobs_module.JobManager, "run_full_job", fake_full)
    monkeypatch.setattr(jobs_module.JobManager, "run_preview_job", fake_preview)


def test_post_jobs_returns_job_id(client, monkeypatch):
    _patch_orchestration(monkeypatch)
    r = client.post("/api/jobs", data={
        "url": "https://www.youtube.com/watch?v=x",
        "model": "realesr-general-x4v3",
        "scale": "4",
        "output_format": "mkv",
    })
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body


def test_post_jobs_rejects_concurrent(client, monkeypatch):
    _patch_orchestration(monkeypatch)
    # Make the first job hang so it stays active.
    from web import jobs as jobs_module

    async def hang(self, job_id, output_dir, **_):
        await asyncio.sleep(5.0)

    monkeypatch.setattr(jobs_module.JobManager, "run_full_job", hang)

    r1 = client.post("/api/jobs", data={"url": "https://x.test/a", "model": "m",
                                        "scale": "4", "output_format": "mkv"})
    assert r1.status_code == 200
    r2 = client.post("/api/jobs", data={"url": "https://x.test/b", "model": "m",
                                        "scale": "4", "output_format": "mkv"})
    assert r2.status_code == 409


def test_get_job_returns_state(client, monkeypatch):
    _patch_orchestration(monkeypatch)
    r = client.post("/api/jobs", data={"url": "https://x.test/a", "model": "m",
                                       "scale": "4", "output_format": "mkv"})
    job_id = r.json()["job_id"]
    # Give the background task a tick.
    import time; time.sleep(0.1)
    r2 = client.get(f"/api/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id


def test_cancel_unknown_job_404(client):
    r = client.post("/api/jobs/does-not-exist/cancel")
    assert r.status_code == 404


def test_post_preview_returns_job_id(client, monkeypatch):
    _patch_orchestration(monkeypatch)
    r = client.post("/api/preview", data={
        "url": "https://x.test/a", "model": "m", "scale": "4",
    })
    assert r.status_code == 200
    assert "job_id" in r.json()


def test_post_jobs_validates_scale(client):
    r = client.post("/api/jobs", data={"url": "u", "model": "m",
                                       "scale": "8", "output_format": "mkv"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_server_jobs.py -v
```

Expected: 404 / 405 errors because routes don't exist.

- [ ] **Step 3: Implement — extend `web/server.py`**

Add these imports near the top:

```python
import asyncio
import re
from typing import Literal

from fastapi import BackgroundTasks, Form, UploadFile, File
from web.workdir import default_output_dir
```

Add a request validator and the routes inside `build_app(...)`, after the existing endpoints:

```python
    @app.post("/api/jobs")
    async def post_job(
        url: str = Form(...),
        model: str = Form(...),
        scale: int = Form(...),
        output_format: Literal["mkv", "mp4"] = Form("mkv"),
        output_dir: Optional[str] = Form(None),
        audio_file: Optional[UploadFile] = File(None),
    ):
        if scale not in (2, 4):
            raise HTTPException(status_code=422, detail="scale must be 2 or 4")
        if not re.match(r"^https?://", url):
            raise HTTPException(status_code=422, detail="url must start with http(s)")
        out = Path(output_dir).expanduser() if output_dir else default_output_dir()
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"output_dir not writable: {exc}")

        if audio_file is not None and audio_file.filename:
            if not audio_file.filename.lower().endswith(".flac"):
                raise HTTPException(status_code=422, detail="audio_file must be .flac")

        try:
            job_id, workdir = job_manager.register_job(
                kind="full", url=url, model=model, scale=scale,
                output_format=output_format, audio_override=None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        if audio_file is not None and audio_file.filename:
            target = workdir / "audio_override.flac"
            with target.open("wb") as f:
                f.write(await audio_file.read())
            job_manager.set_audio_override(job_id, "audio_override.flac")

        async def runner():
            await job_manager.run_full_job(job_id, output_dir=out)

        asyncio.create_task(runner())
        return {"job_id": job_id}

    @app.post("/api/preview")
    async def post_preview(
        url: str = Form(...),
        model: str = Form(...),
        scale: int = Form(...),
    ):
        if scale not in (2, 4):
            raise HTTPException(status_code=422, detail="scale must be 2 or 4")
        if not re.match(r"^https?://", url):
            raise HTTPException(status_code=422, detail="url must start with http(s)")
        try:
            job_id, _ = job_manager.register_job(
                kind="preview", url=url, model=model, scale=scale,
                output_format="mkv",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        async def runner():
            await job_manager.run_preview_job(job_id)

        asyncio.create_task(runner())
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        # Cancellation is best-effort; the orchestrator owns the StageRun, so
        # we use the recorded pid as a hint and let the watcher mark CANCELLED.
        from web.state import JobState
        if JobState(snap["state"]).is_terminal():
            return {"already_terminal": True}
        # Send a SIGTERM via os if pid known
        pid = snap.get("pid")
        if pid:
            import os, signal, sys as _sys
            try:
                if _sys.platform == "win32":
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            job_manager.set_state(job_id, JobState.CANCELLED)
        except Exception:
            pass
        return {"ok": True}
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_server_jobs.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add web/server.py web/tests/test_server_jobs.py
git commit -m "web: HTTP routes for jobs (full, preview, get, cancel)"
```

---

## Task 17: SSE events route + thumbnails + output download

**Files:**
- Modify: `web/server.py`
- Create: `web/tests/test_server_events.py`

- [ ] **Step 1: Write the failing test**

`web/tests/test_server_events.py`:

```python
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.events import CompleteEvent, LogEvent
from web.server import build_app


@pytest.fixture
def app_with_models(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")
    return build_app(models_dir=models_dir, workdir_root=tmp_path / "jobs"), tmp_path


def test_get_thumbnail_returns_jpeg(app_with_models, tmp_path):
    app, root = app_with_models
    client = TestClient(app)

    # Register a job and write a fake thumbnail.
    mgr = app.state.job_manager
    job_id, workdir = mgr.register_job(
        kind="full", url="u", model="m", scale=4, output_format="mkv",
    )
    thumb = workdir / "thumbs" / "up_000123.jpg"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"\xff\xd8\xff\xd9")  # tiny JPEG

    r = client.get(f"/api/jobs/{job_id}/frames/up/000123")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert r.content.startswith(b"\xff\xd8")


def test_get_thumbnail_404_for_unknown_frame(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    r = client.get(f"/api/jobs/{job_id}/frames/up/999999")
    assert r.status_code == 404


def test_events_stream_emits_subscribed_events(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")

    async def producer():
        await asyncio.sleep(0.05)
        await mgr.publish(job_id, LogEvent(line="hello"))
        await asyncio.sleep(0.05)
        await mgr.publish(job_id, CompleteEvent(output="/tmp/x.mkv", size_bytes=1))
        await mgr.close_subscribers(job_id)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(producer())

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        body = b""
        for chunk in resp.iter_bytes():
            body += chunk
            if b'"complete"' in body:
                break
    text = body.decode("utf-8")
    assert "hello" in text
    assert "complete" in text


def test_get_output_returns_file(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, workdir = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    out = workdir / "output" / "x.mkv"
    out.write_bytes(b"\x00" * 10)
    mgr.set_output(job_id, out)

    r = client.get(f"/api/jobs/{job_id}/output")
    assert r.status_code == 200
    assert len(r.content) == 10
```

- [ ] **Step 2: Run, expect failure**

```bash
web/.venv/bin/pytest web/tests/test_server_events.py -v
```

Expected: 404s on the new routes.

- [ ] **Step 3: Implement — extend `web/server.py`**

Add at top of file:

```python
from fastapi.responses import StreamingResponse
```

Add inside `build_app` after the cancel route:

```python
    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        try:
            sub = await job_manager.subscribe(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

        async def stream():
            yield "retry: 3000\n\n"
            async for evt in sub:
                yield evt.to_sse()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/jobs/{job_id}/frames/{kind}/{frame_id}")
    def get_frame(job_id: str, kind: str, frame_id: str):
        if kind not in ("src", "up"):
            raise HTTPException(status_code=400, detail="kind must be src or up")
        if not re.match(r"^[0-9]{6}$", frame_id):
            raise HTTPException(status_code=400, detail="invalid frame_id")
        try:
            workdir = job_manager.workdir.get_workdir(job_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="job not found")
        path = workdir / "thumbs" / f"{kind}_{frame_id}.jpg"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="thumbnail not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/output")
    def get_output(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        out = snap.get("output_path")
        if not out or not Path(out).is_file():
            raise HTTPException(status_code=404, detail="output not available")
        return FileResponse(out, filename=Path(out).name)

    @app.post("/api/jobs/{job_id}/reveal")
    def reveal(job_id: str):
        try:
            snap = job_manager.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        out = snap.get("output_path")
        if not out:
            raise HTTPException(status_code=404, detail="no output yet")
        target = str(Path(out).parent)
        import subprocess as _sp, sys as _sys
        try:
            if _sys.platform == "darwin":
                _sp.Popen(["open", target])
            elif _sys.platform == "win32":
                _sp.Popen(["explorer", target])
            else:
                _sp.Popen(["xdg-open", target])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"ok": True}
```

- [ ] **Step 4: Run, expect pass**

```bash
web/.venv/bin/pytest web/tests/test_server_events.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Run the full test suite to make sure nothing regressed**

```bash
web/.venv/bin/pytest web/tests -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add web/server.py web/tests/test_server_events.py
git commit -m "web: SSE event stream + thumbnail/output/reveal routes"
```

---

## Task 18: Static HTML + CSS

**Files:**
- Create: `web/static/index.html`
- Create: `web/static/style.css`

(No automated tests; manual validation in step 4.)

- [ ] **Step 1: Write `web/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Music Video Upscaler</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <main>
    <h1>Music Video Upscaler</h1>

    <section id="health-banner" class="banner hidden"></section>

    <section id="panel-source" class="panel">
      <h2>1. Source</h2>
      <div class="row">
        <input id="url" type="url" placeholder="https://www.youtube.com/watch?v=..." />
        <button id="btn-probe">Probe</button>
      </div>
      <p id="probe-summary" class="summary"></p>
      <p id="probe-error" class="error hidden"></p>
    </section>

    <section id="panel-settings" class="panel disabled">
      <h2>2. Settings</h2>
      <div class="row">
        <label>Model
          <select id="model"></select>
        </label>
        <label>Scale
          <select id="scale">
            <option value="2">2x</option>
            <option value="4">4x</option>
          </select>
        </label>
        <label>Format
          <select id="output-format">
            <option value="mkv">mkv</option>
            <option value="mp4">mp4</option>
          </select>
        </label>
      </div>
      <div class="row">
        <label>Output folder
          <input id="output-dir" type="text" placeholder="(default per-OS)" />
        </label>
      </div>
      <div class="row">
        <label>Optional FLAC override
          <input id="audio-file" type="file" accept=".flac" />
        </label>
      </div>
      <div class="row">
        <button id="btn-preview" class="secondary">Preview 5 frames</button>
        <button id="btn-run" class="primary">Run</button>
      </div>
    </section>

    <section id="panel-preview" class="panel hidden">
      <h2>3. Preview</h2>
      <p class="summary" id="preview-caption"></p>
      <div id="preview-grid" class="grid"></div>
    </section>

    <section id="panel-progress" class="panel hidden">
      <h2>4. Job</h2>
      <ol id="stages" class="stages">
        <li data-stage="downloading">Downloading</li>
        <li data-stage="preparing">Sync</li>
        <li data-stage="extracting">Extract</li>
        <li data-stage="upscaling">Upscale</li>
        <li data-stage="muxing">Mux</li>
      </ol>
      <div class="progress">
        <div id="progress-bar"></div>
        <span id="progress-text">Starting…</span>
      </div>
      <div id="thumb-strip" class="strip"></div>
      <details>
        <summary>Log</summary>
        <pre id="log"></pre>
      </details>
      <div class="row">
        <button id="btn-cancel" class="danger">Cancel</button>
      </div>
    </section>

    <section id="panel-done" class="panel hidden">
      <h2>5. Done</h2>
      <p id="done-summary" class="summary"></p>
      <div class="row">
        <a id="btn-download" class="button">Download</a>
        <button id="btn-reveal">Reveal in file manager</button>
        <button id="btn-new">New job</button>
      </div>
    </section>
  </main>

  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/static/style.css`**

```css
:root {
  color-scheme: dark;
  --bg: #0f1115;
  --panel: #181b22;
  --border: #2a2f3a;
  --text: #e6e9ef;
  --muted: #8a93a3;
  --accent: #5aa6ff;
  --danger: #ff6b6b;
  --ok: #4cd964;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: -apple-system, system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5;
}
main { max-width: 920px; margin: 0 auto; padding: 24px; }
h1 { font-size: 1.6rem; margin: 0 0 16px; }
h2 { font-size: 1.05rem; margin: 0 0 12px; color: var(--muted); }
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}
.panel.disabled { opacity: 0.5; pointer-events: none; }
.panel.hidden { display: none; }
.row {
  display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
  margin-bottom: 8px;
}
label { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; color: var(--muted); }
input[type=text], input[type=url], select {
  background: #0c0f15; color: var(--text);
  border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; min-width: 200px;
}
input[type=url] { flex: 1; min-width: 320px; }
button, .button {
  background: #2a2f3a; color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 14px; cursor: pointer; text-decoration: none;
}
button.primary { background: var(--accent); border-color: var(--accent); color: #0a0c10; font-weight: 600; }
button.secondary { background: transparent; }
button.danger { color: var(--danger); border-color: var(--danger); }
.summary { color: var(--muted); margin: 8px 0; }
.error { color: var(--danger); }
.banner { padding: 12px; border-radius: 8px; background: #3b1f25; color: var(--danger); margin-bottom: 16px; }
.hidden { display: none; }
.stages { list-style: none; padding: 0; display: flex; gap: 8px; flex-wrap: wrap; }
.stages li { padding: 4px 10px; border-radius: 999px; background: #0c0f15; color: var(--muted); font-size: 0.85rem; }
.stages li.active { background: var(--accent); color: #0a0c10; }
.stages li.done { background: var(--ok); color: #0a0c10; }
.progress { position: relative; height: 24px; background: #0c0f15; border-radius: 8px; margin: 12px 0; overflow: hidden; }
#progress-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 0%; background: var(--accent); transition: width 0.3s; }
#progress-text { position: relative; padding: 4px 10px; font-size: 0.85rem; }
.strip { display: flex; gap: 8px; overflow-x: auto; padding: 8px 0; }
.strip img { height: 80px; border-radius: 4px; border: 1px solid var(--border); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.grid figure { margin: 0; background: #0c0f15; border-radius: 8px; overflow: hidden; }
.grid img { width: 100%; display: block; }
.grid figcaption { padding: 6px 8px; font-size: 0.75rem; color: var(--muted); }
pre { background: #0c0f15; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 0.8rem; max-height: 300px; }
```

- [ ] **Step 3: Boot the server and confirm the page renders**

```bash
web/.venv/bin/uvicorn web.server:app --host 127.0.0.1 --port 8765 &
SERVER_PID=$!
sleep 1
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/
kill $SERVER_PID
```

Expected: `200`.

- [ ] **Step 4: Commit**

```bash
git add web/static/index.html web/static/style.css
git commit -m "web: static index.html + dark CSS"
```

---

## Task 19: Frontend JS

**Files:**
- Create: `web/static/app.js`

(No automated tests for v1 — manual smoke covers it. Spec acknowledged this.)

- [ ] **Step 1: Write `web/static/app.js`**

```js
const $ = (sel) => document.querySelector(sel);

const els = {
  url: $("#url"),
  probe: $("#btn-probe"),
  probeSummary: $("#probe-summary"),
  probeError: $("#probe-error"),
  panelSettings: $("#panel-settings"),
  model: $("#model"),
  scale: $("#scale"),
  outputFormat: $("#output-format"),
  outputDir: $("#output-dir"),
  audioFile: $("#audio-file"),
  preview: $("#btn-preview"),
  run: $("#btn-run"),
  panelPreview: $("#panel-preview"),
  previewCaption: $("#preview-caption"),
  previewGrid: $("#preview-grid"),
  panelProgress: $("#panel-progress"),
  stages: document.querySelectorAll("#stages li"),
  progressBar: $("#progress-bar"),
  progressText: $("#progress-text"),
  thumbStrip: $("#thumb-strip"),
  log: $("#log"),
  cancel: $("#btn-cancel"),
  panelDone: $("#panel-done"),
  doneSummary: $("#done-summary"),
  download: $("#btn-download"),
  reveal: $("#btn-reveal"),
  newJob: $("#btn-new"),
  banner: $("#health-banner"),
};

let activeJobId = null;
let activeEventSource = null;

async function init() {
  const health = await (await fetch("/api/health")).json();
  if (!health.ok) {
    els.banner.textContent =
      "Missing dependencies: " + health.missing.join(", ") +
      " — run install-dependencies.sh / install-dependencies.ps1.";
    els.banner.classList.remove("hidden");
  }
  await loadModels();

  const stored = localStorage.getItem("activeJobId");
  if (stored) {
    try {
      const snap = await (await fetch(`/api/jobs/${stored}`)).json();
      if (snap && snap.state && !["complete", "failed", "cancelled"].includes(snap.state)) {
        activeJobId = stored;
        showProgressPanel();
        attachEvents(stored);
      } else {
        localStorage.removeItem("activeJobId");
      }
    } catch {
      localStorage.removeItem("activeJobId");
    }
  }

  els.probe.addEventListener("click", onProbe);
  els.preview.addEventListener("click", onPreview);
  els.run.addEventListener("click", onRun);
  els.cancel.addEventListener("click", onCancel);
  els.reveal.addEventListener("click", onReveal);
  els.newJob.addEventListener("click", () => location.reload());
  els.model.addEventListener("change", clearPreview);
  els.scale.addEventListener("change", clearPreview);
}

async function loadModels() {
  const models = await (await fetch("/api/models")).json();
  els.model.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.name;
    opt.textContent = m.hint ? `${m.name} — ${m.hint}` : m.name;
    if (m.default) opt.selected = true;
    els.model.appendChild(opt);
  }
}

async function onProbe() {
  els.probeError.classList.add("hidden");
  els.probeSummary.textContent = "Probing…";
  try {
    const r = await fetch("/api/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: els.url.value }),
    });
    if (!r.ok) {
      const err = await r.json();
      els.probeError.textContent = err.detail || "Probe failed";
      els.probeError.classList.remove("hidden");
      els.probeSummary.textContent = "";
      return;
    }
    const meta = await r.json();
    els.probeSummary.textContent =
      `${meta.title} — ${formatDuration(meta.duration)} — ${meta.width}x${meta.height} @ ${meta.fps.toFixed(2)} fps`;
    els.scale.value = String(meta.recommended_scale);
    els.panelSettings.classList.remove("disabled");
  } catch (e) {
    els.probeError.textContent = String(e);
    els.probeError.classList.remove("hidden");
  }
}

function clearPreview() {
  els.panelPreview.classList.add("hidden");
  els.previewGrid.innerHTML = "";
}

async function onPreview() {
  clearPreview();
  const fd = new FormData();
  fd.append("url", els.url.value);
  fd.append("model", els.model.value);
  fd.append("scale", els.scale.value);
  const r = await fetch("/api/preview", { method: "POST", body: fd });
  if (!r.ok) {
    alert((await r.json()).detail || "Preview failed");
    return;
  }
  const { job_id } = await r.json();
  els.panelPreview.classList.remove("hidden");
  els.previewCaption.textContent = `Model: ${els.model.value} • ${els.scale.value}x`;

  const es = new EventSource(`/api/jobs/${job_id}/events`);
  const seen = new Set();
  es.onmessage = (msg) => {
    const evt = JSON.parse(msg.data);
    if (evt.type === "thumbnail" && !seen.has(evt.frame_id + evt.kind)) {
      seen.add(evt.frame_id + evt.kind);
      addPreviewThumb(evt);
    }
    if (evt.type === "complete" || evt.type === "error") {
      es.close();
      if (evt.type === "error") alert("Preview failed: " + evt.message);
    }
  };
}

function addPreviewThumb(evt) {
  let figure = els.previewGrid.querySelector(`figure[data-frame="${evt.frame_id}"]`);
  if (!figure) {
    figure = document.createElement("figure");
    figure.dataset.frame = evt.frame_id;
    const img = document.createElement("img");
    img.alt = evt.frame_id;
    figure.appendChild(img);
    const cap = document.createElement("figcaption");
    figure.appendChild(cap);
    els.previewGrid.appendChild(figure);
  }
  const img = figure.querySelector("img");
  const cap = figure.querySelector("figcaption");
  if (evt.kind === "src") {
    figure.dataset.src = evt.url;
    cap.textContent = `Frame ${evt.frame_id} — hover to see upscaled`;
  } else {
    figure.dataset.up = evt.url;
    img.src = evt.url;
  }
  if (figure.dataset.src && figure.dataset.up) {
    img.src = figure.dataset.up;
    figure.addEventListener("mouseenter", () => { img.src = figure.dataset.src; });
    figure.addEventListener("mouseleave", () => { img.src = figure.dataset.up; });
  }
}

async function onRun() {
  const fd = new FormData();
  fd.append("url", els.url.value);
  fd.append("model", els.model.value);
  fd.append("scale", els.scale.value);
  fd.append("output_format", els.outputFormat.value);
  if (els.outputDir.value) fd.append("output_dir", els.outputDir.value);
  if (els.audioFile.files[0]) fd.append("audio_file", els.audioFile.files[0]);

  const r = await fetch("/api/jobs", { method: "POST", body: fd });
  if (!r.ok) {
    alert((await r.json()).detail || "Failed to start job");
    return;
  }
  const { job_id } = await r.json();
  activeJobId = job_id;
  localStorage.setItem("activeJobId", job_id);
  showProgressPanel();
  attachEvents(job_id);
}

function showProgressPanel() {
  els.panelProgress.classList.remove("hidden");
  els.panelDone.classList.add("hidden");
  els.thumbStrip.innerHTML = "";
  els.log.textContent = "";
  els.progressBar.style.width = "0%";
  els.progressText.textContent = "Starting…";
  els.stages.forEach((li) => li.classList.remove("active", "done"));
}

function attachEvents(jobId) {
  if (activeEventSource) activeEventSource.close();
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  activeEventSource = es;
  es.onmessage = (msg) => {
    const evt = JSON.parse(msg.data);
    handleEvent(evt);
  };
}

function handleEvent(evt) {
  if (evt.type === "stage") {
    els.stages.forEach((li) => {
      if (li.dataset.stage === evt.stage) {
        li.classList.add(evt.status === "done" ? "done" : "active");
        if (evt.status === "done") li.classList.remove("active");
      }
    });
  }
  if (evt.type === "progress") {
    const pct = evt.total ? Math.round((evt.current / evt.total) * 100) : 0;
    els.progressBar.style.width = pct + "%";
    els.progressText.textContent = `${evt.stage} ${evt.current} / ${evt.total} (${pct}%)`;
  }
  if (evt.type === "thumbnail" && evt.kind === "up") {
    const img = document.createElement("img");
    img.src = evt.url;
    img.alt = evt.frame_id;
    els.thumbStrip.appendChild(img);
    while (els.thumbStrip.children.length > 12) {
      els.thumbStrip.removeChild(els.thumbStrip.firstChild);
    }
  }
  if (evt.type === "log") {
    els.log.textContent += evt.line + "\n";
    els.log.scrollTop = els.log.scrollHeight;
  }
  if (evt.type === "complete") {
    els.panelDone.classList.remove("hidden");
    els.doneSummary.textContent = `Output: ${evt.output} (${(evt.size_bytes / 1048576).toFixed(1)} MB)`;
    els.download.href = `/api/jobs/${activeJobId}/output`;
    localStorage.removeItem("activeJobId");
    if (activeEventSource) activeEventSource.close();
  }
  if (evt.type === "error") {
    alert("Job failed: " + evt.message);
    localStorage.removeItem("activeJobId");
  }
}

async function onCancel() {
  if (!activeJobId) return;
  await fetch(`/api/jobs/${activeJobId}/cancel`, { method: "POST" });
}

async function onReveal() {
  if (!activeJobId) return;
  await fetch(`/api/jobs/${activeJobId}/reveal`, { method: "POST" });
}

function formatDuration(s) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

init();
```

- [ ] **Step 2: Boot server, open browser, sanity-check**

```bash
web/.venv/bin/uvicorn web.server:app --host 127.0.0.1 --port 8765 &
SERVER_PID=$!
sleep 1
echo "Open http://127.0.0.1:8765/ in a browser. Verify panels render."
read -p "Press enter when verified, then ^C..."
kill $SERVER_PID
```

- [ ] **Step 3: Commit**

```bash
git add web/static/app.js
git commit -m "web: frontend app.js (probe, preview, run, progress, done)"
```

---

## Task 20: Server launchers

**Files:**
- Create: `web/run_server.sh`
- Create: `web/run_server.ps1`

- [ ] **Step 1: Write `web/run_server.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating venv at $VENV..."
  python3 -m venv "$VENV"
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

echo "Starting music-video-upscaler web UI on http://$HOST:$PORT"
exec "$PY" -m uvicorn web.server:app --host "$HOST" --port "$PORT"
```

`chmod +x web/run_server.sh`

- [ ] **Step 2: Write `web/run_server.ps1`**

```powershell
[CmdletBinding()]
param(
  [string]$WebHost = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Venv = Join-Path $ScriptDir ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
  Write-Host "Creating venv at $Venv..."
  python -m venv $Venv
  & $Py -m pip install --upgrade pip | Out-Null
  & $Py -m pip install -r (Join-Path $ScriptDir "requirements.txt")
}

Push-Location $RepoRoot
try {
  Write-Host "Starting music-video-upscaler web UI on http://${WebHost}:$Port"
  & $Py -m uvicorn web.server:app --host $WebHost --port $Port
} finally {
  Pop-Location
}
```

- [ ] **Step 3: Smoke-run the launcher**

```bash
./web/run_server.sh &
SERVER_PID=$!
sleep 2
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/health
kill $SERVER_PID
```

Expected: `200`.

- [ ] **Step 4: Commit**

```bash
git add web/run_server.sh web/run_server.ps1
git commit -m "web: launchers (run_server.sh + run_server.ps1)"
```

---

## Task 21: Installer integration

**Files:**
- Modify: `install-dependencies.sh`
- Modify: `windows/install-dependencies.ps1`

- [ ] **Step 1: Read current installer flag handling**

```bash
head -n 60 install-dependencies.sh
head -n 80 windows/install-dependencies.ps1
```

Identify where flags are parsed (or where to add parsing).

- [ ] **Step 2: Add `--with-web` to `install-dependencies.sh`**

Insert near the top (after `set -euo pipefail`):

```bash
WITH_WEB=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --with-web) WITH_WEB=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]:-}"
```

At the end of the script (before any final summary `echo`), append:

```bash
if [[ "$WITH_WEB" -eq 1 ]]; then
  echo ""
  echo "Installing web UI dependencies..."
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PYTHON="${PYTHON:-python3}"
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "WARNING: python3 not found; skipping web UI install." >&2
  else
    "$PYTHON" -m venv "$REPO_ROOT/web/.venv"
    "$REPO_ROOT/web/.venv/bin/pip" install --upgrade pip >/dev/null
    "$REPO_ROOT/web/.venv/bin/pip" install -r "$REPO_ROOT/web/requirements.txt"
    echo "Web UI installed. Run with: ./web/run_server.sh"
  fi
fi
```

- [ ] **Step 3: Add `-WithWeb` switch to `windows/install-dependencies.ps1`**

Add to the param block at the top:

```powershell
[switch]$WithWeb,
```

At the end (before any final summary), append:

```powershell
if ($WithWeb) {
  Write-Host ""
  Write-Host "Installing web UI dependencies..."
  $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
  $WebDir = Join-Path $RepoRoot "web"
  $Venv = Join-Path $WebDir ".venv"
  python -m venv $Venv
  & (Join-Path $Venv "Scripts\pip.exe") install --upgrade pip | Out-Null
  & (Join-Path $Venv "Scripts\pip.exe") install -r (Join-Path $WebDir "requirements.txt")
  Write-Host "Web UI installed. Run with: web\run_server.ps1"
}
```

- [ ] **Step 4: Smoke-test on this host**

```bash
./install-dependencies.sh --with-web
ls web/.venv/bin/uvicorn
```

Expected: file exists.

- [ ] **Step 5: Commit**

```bash
git add install-dependencies.sh windows/install-dependencies.ps1
git commit -m "installers: --with-web / -WithWeb to provision web UI venv"
```

---

## Task 22: Integration smoke test (synthetic 2s video)

**Files:**
- Create: `web/tests/test_pipeline_smoke.py`

- [ ] **Step 1: Write the test**

`web/tests/test_pipeline_smoke.py`:

```python
"""End-to-end test that exercises the real stage scripts on a tiny synthetic video.

Skipped automatically if any required external tool is missing.
"""
import asyncio
import os
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
def tiny_video(tmp_path_factory) -> Path:
    """Synthesize a 2s 64x36 test pattern + silent audio."""
    out = FIXTURES / "tiny.mkv"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=64x36:rate=10:duration=2",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(out),
        ], check=True, capture_output=True)
    return out


@pytest.mark.asyncio
async def test_full_pipeline_against_tiny_video(tiny_video, tmp_path, monkeypatch):
    from web.jobs import JobManager

    # Skip the real download by pre-seeding the source dir and patching the download stage.
    mgr = JobManager(workdir_root=tmp_path / "jobs")
    job_id, workdir = mgr.register_job(
        kind="full", url="local://tiny", model="realesr-general-x4v3",
        scale=4, output_format="mkv",
    )
    src_dir = workdir / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tiny_video, src_dir / "video.mkv")
    # Pull audio out for the sync stage to consume.
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y", "-i", str(tiny_video),
        "-vn", "-c:a", "flac", str(src_dir / "audio.flac"),
    ], check=True, capture_output=True)

    # Patch the download portion of run_full_job by skipping straight into stages
    # — call the script wrappers directly via the sync_audio onwards path.
    from web.platform_info import REPO_ROOT, stage_command
    from web.subprocess_runner import StageRun, run_stage
    from web.events import LogEvent
    from web.state import JobState

    async def _line(line: str) -> None:
        pass

    # sync_audio
    mgr.set_state(job_id, JobState.DOWNLOADING)
    mgr.set_state(job_id, JobState.PREPARING)
    rc = await run_stage(StageRun(
        cmd=stage_command("sync_audio", [str(src_dir / "video.mkv"), str(src_dir / "audio.flac")]),
        cwd=REPO_ROOT,
        log_path=mgr.workdir.log_path(job_id),
        on_line=_line,
    ))
    assert rc == 0
    synced = src_dir / "video_synced.flac"
    assert synced.is_file()

    # extract
    mgr.set_state(job_id, JobState.EXTRACTING)
    frames = workdir / "tmp_frames"
    rc = await run_stage(StageRun(
        cmd=stage_command("extract", [str(src_dir / "video.mkv"), str(frames)]),
        cwd=REPO_ROOT,
        log_path=mgr.workdir.log_path(job_id),
        on_line=_line,
    ))
    assert rc == 0
    assert any(frames.glob("*.png"))

    # upscale
    mgr.set_state(job_id, JobState.UPSCALING)
    upscaled = workdir / "tmp_upscaled_4x"
    rc = await run_stage(StageRun(
        cmd=stage_command("upscale", [str(frames), str(upscaled), "4", "realesr-general-x4v3"]),
        cwd=REPO_ROOT,
        log_path=mgr.workdir.log_path(job_id),
        on_line=_line,
    ))
    assert rc == 0
    assert any(upscaled.glob("*.png"))

    # mux
    mgr.set_state(job_id, JobState.MUXING)
    out = workdir / "output" / "tiny_upscaled.mkv"
    rc = await run_stage(StageRun(
        cmd=stage_command("mux", [str(upscaled), str(synced), str(out), str(src_dir / "video.mkv")]),
        cwd=REPO_ROOT,
        log_path=mgr.workdir.log_path(job_id),
        on_line=_line,
    ))
    assert rc == 0
    assert out.is_file()
    assert out.stat().st_size > 0

    mgr.set_state(job_id, JobState.COMPLETE)
```

- [ ] **Step 2: Run the smoke test**

```bash
web/.venv/bin/pytest web/tests/test_pipeline_smoke.py -v
```

Expected: `1 passed` if the host has `ffmpeg`, `ffprobe`, `realesrgan-ncnn-vulkan`, and the default model. Otherwise `1 skipped`.

- [ ] **Step 3: Commit**

```bash
git add web/tests/test_pipeline_smoke.py
git commit -m "web: end-to-end smoke test on synthesized 2s video"
```

---

## Task 23: Manual smoke checklist + README

**Files:**
- Create: `web/tests/manual_smoke.md`
- Create: `web/README.md`

- [ ] **Step 1: Write `web/tests/manual_smoke.md`**

```markdown
# Manual smoke test — web UI

Use a real, public, short YouTube music video (≤ 2 minutes) you don't mind re-running.

## Setup
1. `./install-dependencies.sh --with-web` (or Windows equivalent).
2. `./web/run_server.sh` (or `.ps1`).
3. Open `http://127.0.0.1:8765/` in a browser.

## Checklist
- [ ] No red banner. (If yes, fix missing deps and retry.)
- [ ] Model dropdown lists at least `realesr-general-x4v3`, default selected.
- [ ] Paste URL, click **Probe**. Summary appears with title, duration, resolution, fps.
- [ ] Scale auto-selects (`2x` for 1080p+, `4x` otherwise).
- [ ] Click **Preview**. After ~30s, 5 thumbnails appear. Hover swaps src/upscaled.
- [ ] Change model, preview clears.
- [ ] Click **Run**. Stage indicator advances: Downloading → Sync → Extract → Upscale → Mux.
- [ ] During Upscale, thumbnails stream into the strip.
- [ ] Refresh the browser mid-Upscale; UI reattaches and resumes from current state.
- [ ] Click **Cancel** during a run. Job state becomes `cancelled` within ~10s.
- [ ] Run to completion. Done panel shows output path + size.
- [ ] **Download** returns the file. **Reveal in file manager** opens the folder.
- [ ] **New job** resets the form.
```

- [ ] **Step 2: Write `web/README.md`**

```markdown
# Web UI

Thin local web UI for the music-video upscaling pipeline. Paste a YouTube URL,
pick a model and scale, optionally upload a FLAC, preview a few sample frames,
and watch the full upscale stream live.

## Install

```bash
./install-dependencies.sh --with-web
```

(or `windows\install-dependencies.ps1 -WithWeb`)

## Run

```bash
./web/run_server.sh         # macOS/Linux
web\run_server.ps1          # Windows
```

Open `http://127.0.0.1:8765/`.

## Override host/port

```bash
HOST=0.0.0.0 PORT=9000 ./web/run_server.sh
```

> **Note:** binding to `0.0.0.0` exposes the server to your LAN. There is no
> authentication. Only do this on trusted networks.

## What it actually does

The server is a thin shell over the existing pipeline scripts
(`00_sanitize.sh`…`04_mux.sh` on POSIX, `windows\*.ps1` on Windows). It runs
each stage as its own subprocess, streams stdout into the browser via
Server-Sent Events, and serves a few thumbnails so you can see results.

Job artifacts are stored under
`~/.cache/music-video-upscaler/jobs/<job_id>/` (XDG-respecting on Linux,
`~/Library/Caches/...` on macOS, `%LOCALAPPDATA%\...` on Windows). The final
muxed file is symlinked into your output folder (default `~/Movies/MusicVideoUpscaled/`
on macOS, `~/Videos/MusicVideoUpscaled/` elsewhere).

Old workdirs (>7 days) are cleaned up at startup, except the most recent 5 and
any non-terminal jobs.

## Tests

```bash
web/.venv/bin/pytest web/tests
```

The integration smoke test (`test_pipeline_smoke.py`) is skipped automatically
when ffmpeg, ffprobe, realesrgan-ncnn-vulkan, or the default model are missing.

## Design

See `docs/superpowers/specs/2026-05-11-web-frontend-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add web/tests/manual_smoke.md web/README.md
git commit -m "web: manual smoke checklist + README"
```

---

## Task 24: Final regression sweep + working-tree clean

- [ ] **Step 1: Run the full test suite**

```bash
web/.venv/bin/pytest web/tests -v
```

Expected: all unit tests pass; `test_pipeline_smoke.py` either passes or skips with a clear reason.

- [ ] **Step 2: Boot the server one last time and walk the manual checklist**

Follow `web/tests/manual_smoke.md` end to end.

- [ ] **Step 3: Confirm working tree is clean**

```bash
git status
git log --oneline origin/master..HEAD
```

- [ ] **Step 4: Optional — push**

```bash
# Only if user explicitly requests it.
git push origin master
```
