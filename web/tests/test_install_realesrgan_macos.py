import os
import shutil
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


def _make_fake_archive(tmp_path: Path, *, help_exit_code: int = 0) -> Path:
    payload = tmp_path / "payload" / "realesrgan-ncnn-vulkan-20220424-macos" / "realesrgan-ncnn-vulkan"
    _write_executable(
        payload,
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == \"-h\" ]]; then\n"
        "  echo fake-help\n"
        f"  exit {help_exit_code}\n"
        "fi\n"
        "exit 0\n",
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only installer smoke")
def test_install_realesrgan_macos_wraps_nonzero_help_exit(tmp_path):
    archive = _make_fake_archive(tmp_path, help_exit_code=255)
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

    help_run = subprocess.run(
        [str(tools_dir / "realesrgan-ncnn-vulkan"), "-h"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "fake-help" in help_run.stdout


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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only installer integration")
def test_install_dependencies_macos_skips_helper_when_env_override_is_valid(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copy2(REPO_ROOT / "install-dependencies.sh", workspace / "install-dependencies.sh")
    shutil.copy2(REPO_ROOT / "install-realesrgan-macos.sh", workspace / "install-realesrgan-macos.sh")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        _write_executable(bin_dir / tool, "#!/usr/bin/env bash\nexit 0\n")

    env_realesrgan = tmp_path / "custom-realesrgan"
    _write_executable(env_realesrgan, "#!/usr/bin/env bash\nexit 0\n")

    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REALESRGAN_BIN": str(env_realesrgan),
        "REALESRGAN_MACOS_URL": "file:///definitely-missing-realesrgan.zip",
    }

    completed = subprocess.run(
        ["bash", "install-dependencies.sh"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    installed = workspace / "tools" / "realesrgan-ncnn-vulkan"
    assert not installed.exists()
    assert "realesrgan-ncnn-vulkan: NOT INSTALLED" not in completed.stdout
    assert "realesrgan-ncnn-vulkan: OK" in completed.stdout
