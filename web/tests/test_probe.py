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
