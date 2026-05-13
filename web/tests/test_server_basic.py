from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.server import build_app


def _seed_models_dir(models_dir: Path) -> Path:
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")
    return models_dir


@pytest.fixture
def client(tmp_path):
    models_dir = _seed_models_dir(tmp_path / "models")

    app = build_app(models_dir=models_dir, workdir_root=tmp_path / "jobs")
    return TestClient(app)


def test_health_returns_200(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert "missing" in body


def test_health_honors_executable_realesrgan_bin(tmp_path, monkeypatch):
    from web import server as server_module

    models_dir = _seed_models_dir(tmp_path / "models")
    custom_bin = tmp_path / "custom" / "realesrgan-ncnn-vulkan"
    custom_bin.parent.mkdir()
    custom_bin.write_text("#!/bin/sh\n")
    custom_bin.chmod(0o755)

    monkeypatch.setattr(server_module, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("REALESRGAN_BIN", str(custom_bin))

    def fake_which(tool):
        if tool in ("ffmpeg", "ffprobe", "yt-dlp"):
            return f"/usr/bin/{tool}"
        if tool == "realesrgan-ncnn-vulkan":
            return None
        raise AssertionError(f"unexpected tool lookup: {tool}")

    monkeypatch.setattr(server_module.shutil, "which", fake_which)

    health = server_module._check_health(models_dir)

    assert "realesrgan-ncnn-vulkan" not in health["missing"]


def test_health_rejects_non_executable_repo_local_candidates(tmp_path, monkeypatch):
    from web import server as server_module

    models_dir = _seed_models_dir(tmp_path / "models")
    repo_bin = tmp_path / "tools" / "realesrgan-ncnn-vulkan"
    repo_bin.parent.mkdir()
    repo_bin.write_text("#!/bin/sh\n")
    repo_bin.chmod(0o644)
    windows_bin = tmp_path / "windows" / "realesrgan-ncnn-vulkan.exe"
    windows_bin.parent.mkdir()
    windows_bin.write_text("not executable")
    windows_bin.chmod(0o644)

    monkeypatch.setattr(server_module, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("REALESRGAN_BIN", raising=False)

    def fake_which(tool):
        if tool in ("ffmpeg", "ffprobe", "yt-dlp"):
            return f"/usr/bin/{tool}"
        if tool == "realesrgan-ncnn-vulkan":
            return None
        raise AssertionError(f"unexpected tool lookup: {tool}")

    monkeypatch.setattr(server_module.shutil, "which", fake_which)

    health = server_module._check_health(models_dir)

    assert "realesrgan-ncnn-vulkan" in health["missing"]


def test_health_accepts_executable_repo_local_candidate(tmp_path, monkeypatch):
    from web import server as server_module

    models_dir = _seed_models_dir(tmp_path / "models")
    repo_bin = tmp_path / "tools" / "realesrgan-ncnn-vulkan"
    repo_bin.parent.mkdir()
    repo_bin.write_text("#!/bin/sh\n")
    repo_bin.chmod(0o755)

    monkeypatch.setattr(server_module, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("REALESRGAN_BIN", raising=False)

    def fake_which(tool):
        if tool in ("ffmpeg", "ffprobe", "yt-dlp"):
            return f"/usr/bin/{tool}"
        if tool == "realesrgan-ncnn-vulkan":
            return None
        raise AssertionError(f"unexpected tool lookup: {tool}")

    monkeypatch.setattr(server_module.shutil, "which", fake_which)

    health = server_module._check_health(models_dir)

    assert "realesrgan-ncnn-vulkan" not in health["missing"]


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
    # The index.html and style.css are now committed; / must return the page.
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Music Video Upscaler" in r.text


def test_static_css_is_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")


def test_static_js_is_served_and_referenced(client):
    """index.html must reference /static/app.js, and the file must be served."""
    page = client.get("/")
    assert "/static/app.js" in page.text
    js = client.get("/static/app.js")
    assert js.status_code == 200
    # JS is served as application/javascript or text/javascript depending on
    # platform mimetypes; either is acceptable.
    assert "javascript" in js.headers["content-type"]


def test_index_html_contains_theme_toggle(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="theme-toggle"' in r.text
    assert 'id="theme-label"' in r.text


def test_static_js_contains_theme_bootstrap(client):
    js = client.get("/static/app.js")
    assert js.status_code == 200
    body = js.text
    assert "music-video-upscaler.theme" in body
    assert "prefers-color-scheme: dark" in body


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
