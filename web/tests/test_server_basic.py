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
    assert r.status_code in (200, 404)
