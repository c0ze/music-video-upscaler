# macOS Real-ESRGAN Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS installer helper for `realesrgan-ncnn-vulkan`, wire it into `install-dependencies.sh`, and make the web health check recognize `REALESRGAN_BIN`.

**Architecture:** Keep the runtime pipeline untouched. Add a standalone repo-root shell helper that downloads and installs the upstream macOS Real-ESRGAN binary into `tools/`, update `install-dependencies.sh` to call that helper on macOS when the binary is missing, and align `web/server.py` health detection with the pipeline's resolution rules by treating `REALESRGAN_BIN` and executable repo-local binaries as valid.

**Tech Stack:** Bash shell scripting, FastAPI health checks, pytest, subprocess-based smoke tests, repo-local `tools/` binaries

---

## File map

- `install-realesrgan-macos.sh` (new): macOS-only helper that downloads, extracts, validates, and exposes a stable `tools/realesrgan-ncnn-vulkan` entry point.
- `install-dependencies.sh`: invokes the new helper automatically on macOS when Real-ESRGAN is missing.
- `web/server.py`: health check updated to honor `REALESRGAN_BIN` and require executable repo-local binaries.
- `web/tests/test_server_basic.py`: regression coverage for the health-check behavior.
- `web/tests/test_install_realesrgan_macos.py` (new): subprocess smoke tests for the standalone helper and the installer integration path.
- `web/README.md`: document the automatic macOS install path and the standalone recovery command.

### Task 1: Align the web health check with pipeline resolution

**Files:**
- Modify: `web/tests/test_server_basic.py`
- Modify: `web/server.py`
- Test: `web/tests/test_server_basic.py`

- [ ] **Step 1: Write the failing health-check tests**

Add these tests near the existing `/api/health` coverage in `web/tests/test_server_basic.py`:

```python
import os


def test_health_accepts_realesrgan_bin_env_override(tmp_path, monkeypatch):
    from web import server as server_module

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")

    fake_bin = tmp_path / "custom-realesrgan"
    fake_bin.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_bin.chmod(0o755)

    def fake_which(name):
        base = {
            "ffmpeg": "/usr/bin/ffmpeg",
            "ffprobe": "/usr/bin/ffprobe",
            "yt-dlp": "/usr/bin/yt-dlp",
        }
        return base.get(name)

    monkeypatch.setenv("REALESRGAN_BIN", str(fake_bin))
    monkeypatch.setattr(server_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server_module.shutil, "which", fake_which)

    body = server_module._check_health(models_dir)
    assert "realesrgan-ncnn-vulkan" not in body["missing"]
    assert body["ok"] is True


def test_health_rejects_non_executable_realesrgan_candidates(tmp_path, monkeypatch):
    from web import server as server_module

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")

    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    bogus = tools_dir / "realesrgan-ncnn-vulkan"
    bogus.write_text("not executable")

    def fake_which(name):
        base = {
            "ffmpeg": "/usr/bin/ffmpeg",
            "ffprobe": "/usr/bin/ffprobe",
            "yt-dlp": "/usr/bin/yt-dlp",
        }
        return base.get(name)

    monkeypatch.delenv("REALESRGAN_BIN", raising=False)
    monkeypatch.setattr(server_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(server_module.shutil, "which", fake_which)

    body = server_module._check_health(models_dir)
    assert "realesrgan-ncnn-vulkan" in body["missing"]
    assert body["ok"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py -v
```

Expected: FAIL because `_check_health()` ignores `REALESRGAN_BIN` and only checks whether repo-local candidates exist, not whether they are executable.

- [ ] **Step 3: Implement the minimal health-check fix in `web/server.py`**

Add a small executable-path helper and update `_check_health()` to honor `REALESRGAN_BIN` first:

```python
import os
```

```python
def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _check_health(models_dir: Path) -> dict:
    missing = []
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        if shutil.which(tool) is None:
            missing.append(tool)

    env_bin = os.environ.get("REALESRGAN_BIN")
    env_ok = bool(env_bin) and _is_executable_file(Path(env_bin))
    realesr_candidates = [
        REPO_ROOT / "tools" / "realesrgan-ncnn-vulkan",
        REPO_ROOT / "windows" / "realesrgan-ncnn-vulkan.exe",
    ]
    local_ok = any(_is_executable_file(path) for path in realesr_candidates)
    path_ok = shutil.which("realesrgan-ncnn-vulkan") is not None

    if not (env_ok or local_ok or path_ok):
        missing.append("realesrgan-ncnn-vulkan")

    if not list_models(models_dir):
        missing.append("models")
    return {"ok": not missing, "missing": missing}
```

- [ ] **Step 4: Run the tests again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_server_basic.py -v
```

Expected: PASS

### Task 2: Add the standalone macOS installer helper

**Files:**
- Create: `install-realesrgan-macos.sh`
- Create: `web/tests/test_install_realesrgan_macos.py`
- Test: `web/tests/test_install_realesrgan_macos.py`

- [ ] **Step 1: Write the failing smoke test for the standalone helper**

Create `web/tests/test_install_realesrgan_macos.py` with this test:

```python
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755)


def _make_fake_archive(tmp_path: Path) -> Path:
    payload = tmp_path / "payload" / "realesrgan-ncnn-vulkan-20220424-macos" / "realesrgan-ncnn-vulkan"
    _write_executable(
        payload,
        "#!/usr/bin/env bash\nif [[ \"${1:-}\" == \"-h\" ]]; then\n  echo fake-help\n  exit 0\nfi\nexit 0\n",
    )
    archive = tmp_path / "realesrgan-macos.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(
            payload,
            arcname="realesrgan-ncnn-vulkan-20220424-macos/realesrgan-ncnn-vulkan",
        )
    return archive


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only installer smoke")
def test_install_realesrgan_macos_installs_binary_from_override_url(tmp_path):
    archive = _make_fake_archive(tmp_path)
    tools_dir = tmp_path / "tools"

    env = os.environ | {
        "REALESRGAN_MACOS_URL": archive.as_uri(),
        "TOOLS_DIR": str(tools_dir),
    }

    subprocess.run(
        ["bash", str(REPO_ROOT / "install-realesrgan-macos.sh")],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )

    installed = tools_dir / "realesrgan-ncnn-vulkan"
    assert installed.exists()
    assert os.access(installed, os.X_OK)

    help_run = subprocess.run(
        [str(installed), "-h"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "fake-help" in help_run.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
web/.venv/bin/pytest web/tests/test_install_realesrgan_macos.py::test_install_realesrgan_macos_installs_binary_from_override_url -v
```

Expected: FAIL because `install-realesrgan-macos.sh` does not exist yet.

- [ ] **Step 3: Implement `install-realesrgan-macos.sh`**

Create the full helper script:

```bash
#!/usr/bin/env bash
set -euo pipefail

have_cmd() { command -v "$1" >/dev/null 2>&1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TOOLS_DIR:-${ROOT}/tools}"
URL="${REALESRGAN_MACOS_URL:-https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip}"
ARCHIVE="${TOOLS_DIR}/realesrgan-ncnn-vulkan-macos.zip"
EXTRACT_DIR="${TOOLS_DIR}/realesrgan-ncnn-vulkan-macos"
STABLE_BIN="${TOOLS_DIR}/realesrgan-ncnn-vulkan"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper only supports macOS." >&2
  exit 1
fi

mkdir -p "${TOOLS_DIR}"

if [[ -x "${STABLE_BIN}" ]] && "${STABLE_BIN}" -h >/dev/null 2>&1; then
  echo "Real-ESRGAN already installed at ${STABLE_BIN}"
  exit 0
fi

if have_cmd curl; then
  curl -fsSL -o "${ARCHIVE}" "${URL}"
elif have_cmd wget; then
  wget -q -O "${ARCHIVE}" "${URL}"
else
  echo "Need curl or wget to download Real-ESRGAN." >&2
  exit 1
fi

if ! have_cmd unzip; then
  echo "unzip is required to extract Real-ESRGAN." >&2
  exit 1
fi

rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}"
unzip -qo "${ARCHIVE}" -d "${EXTRACT_DIR}"

BIN="$(find "${EXTRACT_DIR}" -type f -name 'realesrgan-ncnn-vulkan' | head -1)"
if [[ -z "${BIN}" || ! -f "${BIN}" ]]; then
  echo "Could not locate realesrgan-ncnn-vulkan in ${EXTRACT_DIR}" >&2
  exit 1
fi

chmod +x "${BIN}"
ln -sfn "${BIN}" "${STABLE_BIN}"
"${STABLE_BIN}" -h >/dev/null
echo "Installed Real-ESRGAN to ${STABLE_BIN}"
```

Then make it executable:

```bash
chmod +x install-realesrgan-macos.sh
```

- [ ] **Step 4: Run the standalone smoke test again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_install_realesrgan_macos.py::test_install_realesrgan_macos_installs_binary_from_override_url -v
```

Expected: PASS

### Task 3: Wire the helper into the main installer and document it

**Files:**
- Modify: `web/tests/test_install_realesrgan_macos.py`
- Modify: `install-dependencies.sh`
- Modify: `web/README.md`
- Test: `web/tests/test_install_realesrgan_macos.py`

- [ ] **Step 1: Write the failing installer-integration test**

Extend `web/tests/test_install_realesrgan_macos.py` with a second smoke test:

```python
import shutil
```

```python
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only installer integration")
def test_install_dependencies_macos_invokes_helper_when_realesrgan_missing(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copy2(REPO_ROOT / "install-dependencies.sh", workspace / "install-dependencies.sh")
    shutil.copy2(REPO_ROOT / "install-realesrgan-macos.sh", workspace / "install-realesrgan-macos.sh")

    archive = _make_fake_archive(tmp_path / "integration")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        _write_executable(bin_dir / tool, "#!/usr/bin/env bash\nexit 0\n")

    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REALESRGAN_MACOS_URL": archive.as_uri(),
    }

    subprocess.run(
        ["bash", "install-dependencies.sh"],
        cwd=workspace,
        env=env,
        check=True,
    )

    installed = workspace / "tools" / "realesrgan-ncnn-vulkan"
    assert installed.exists()
    assert os.access(installed, os.X_OK)
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run:

```bash
web/.venv/bin/pytest web/tests/test_install_realesrgan_macos.py::test_install_dependencies_macos_invokes_helper_when_realesrgan_missing -v
```

Expected: FAIL because `install-dependencies.sh` still prints macOS instructions instead of invoking the helper automatically.

- [ ] **Step 3: Update `install-dependencies.sh` and `web/README.md`**

Patch the macOS Real-ESRGAN branch in `install-dependencies.sh` so it auto-installs when missing:

```bash
else
  if ! have_cmd realesrgan-ncnn-vulkan && [[ ! -x "${TOOLS}/realesrgan-ncnn-vulkan" ]]; then
    if [[ "${OS}" == "Darwin" ]]; then
      "${ROOT}/install-realesrgan-macos.sh"
    else
      log "Real-ESRGAN ncnn Vulkan not found."
      log "Linux x86_64: re-run with INSTALL_REALESRGAN=1"
      log "Windows: place portable build under windows\\"
      log "macOS: install or build a Vulkan binary and export REALESRGAN_BIN=... or put it in tools/"
    fi
  fi
fi
```

Update `web/README.md` so the install path and fallback helper are explicit:

```md
On macOS, `./install-dependencies.sh --with-web` now downloads the upstream
`realesrgan-ncnn-vulkan` archive into `tools/` automatically when the binary is
missing.

If you need to rerun only that step, run `./install-realesrgan-macos.sh`.
```

- [ ] **Step 4: Run the integration test again**

Run:

```bash
web/.venv/bin/pytest web/tests/test_install_realesrgan_macos.py::test_install_dependencies_macos_invokes_helper_when_realesrgan_missing -v
```

Expected: PASS

### Task 4: Regression verification

**Files:**
- Modify: none
- Test: `web/tests`, install scripts, README

- [ ] **Step 1: Run the focused automated regression suite**

Run:

```bash
web/.venv/bin/pytest \
  web/tests/test_server_basic.py \
  web/tests/test_install_realesrgan_macos.py -v
```

Expected: PASS

- [ ] **Step 2: Run the full web test suite**

Run:

```bash
web/.venv/bin/pytest web/tests -q
```

Expected: PASS (with existing environment-dependent skips unchanged)

- [ ] **Step 3: Manually verify the real installer path**

Run:

```bash
./install-realesrgan-macos.sh
./tools/realesrgan-ncnn-vulkan -h
./install-dependencies.sh --with-web
```

Expected:

- the helper succeeds without a source build
- `./tools/realesrgan-ncnn-vulkan -h` exits `0`
- rerunning `./install-dependencies.sh --with-web` leaves the install healthy

- [ ] **Step 4: Manually verify the health banner path**

Run:

```bash
./web/run_server.sh
```

Then, in a second shell:

```bash
curl -s http://127.0.0.1:8765/api/health
```

Expected: the JSON response does not list `realesrgan-ncnn-vulkan` in `missing`.
