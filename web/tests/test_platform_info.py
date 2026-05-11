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
