import asyncio
import time

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
        self.set_state(job_id, JobState.COMPLETE)

    monkeypatch.setattr(jobs_module.JobManager, "run_full_job", fake_full)
    monkeypatch.setattr(jobs_module.JobManager, "run_preview_job", fake_preview)


def test_post_jobs_returns_job_id(client, monkeypatch, tmp_path):
    _patch_orchestration(monkeypatch)
    out = tmp_path / "out"
    r = client.post("/api/jobs", data={
        "url": "https://www.youtube.com/watch?v=x",
        "model": "realesr-general-x4v3",
        "scale": "4",
        "output_format": "mkv",
        "output_dir": str(out),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "job_id" in body


def test_post_jobs_rejects_concurrent(client, monkeypatch, tmp_path):
    from web import jobs as jobs_module

    async def hang(self, job_id, output_dir, **_):
        await asyncio.sleep(5.0)

    monkeypatch.setattr(jobs_module.JobManager, "run_full_job", hang)

    out = tmp_path / "out"
    r1 = client.post("/api/jobs", data={
        "url": "https://x.test/a", "model": "m",
        "scale": "4", "output_format": "mkv",
        "output_dir": str(out),
    })
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/jobs", data={
        "url": "https://x.test/b", "model": "m",
        "scale": "4", "output_format": "mkv",
        "output_dir": str(out),
    })
    assert r2.status_code == 409


def test_get_job_returns_state(client, monkeypatch, tmp_path):
    _patch_orchestration(monkeypatch)
    out = tmp_path / "out"
    r = client.post("/api/jobs", data={
        "url": "https://x.test/a", "model": "m",
        "scale": "4", "output_format": "mkv",
        "output_dir": str(out),
    })
    job_id = r.json()["job_id"]
    time.sleep(0.1)
    r2 = client.get(f"/api/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id


def test_get_unknown_job_returns_404(client):
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404


def test_cancel_unknown_job_404(client):
    r = client.post("/api/jobs/does-not-exist/cancel")
    assert r.status_code == 404


def test_cancel_terminal_job_is_noop(client, monkeypatch, tmp_path):
    _patch_orchestration(monkeypatch)
    out = tmp_path / "out"
    r = client.post("/api/jobs", data={
        "url": "https://x.test/a", "model": "m",
        "scale": "4", "output_format": "mkv",
        "output_dir": str(out),
    })
    job_id = r.json()["job_id"]
    # Wait for fake_full to finish quickly.
    for _ in range(50):
        time.sleep(0.02)
        snap = client.get(f"/api/jobs/{job_id}").json()
        if snap["state"] == "complete":
            break
    r2 = client.post(f"/api/jobs/{job_id}/cancel")
    assert r2.status_code == 200
    assert r2.json().get("already_terminal") is True


def test_post_preview_returns_job_id(client, monkeypatch):
    _patch_orchestration(monkeypatch)
    r = client.post("/api/preview", data={
        "url": "https://x.test/a", "model": "m", "scale": "4",
    })
    assert r.status_code == 200, r.text
    assert "job_id" in r.json()


def test_post_jobs_validates_scale(client, tmp_path):
    out = tmp_path / "out"
    r = client.post("/api/jobs", data={
        "url": "https://x.test/a", "model": "m",
        "scale": "8", "output_format": "mkv",
        "output_dir": str(out),
    })
    assert r.status_code == 422


def test_post_jobs_validates_url_scheme(client, tmp_path):
    out = tmp_path / "out"
    r = client.post("/api/jobs", data={
        "url": "ftp://x.test/a", "model": "m",
        "scale": "4", "output_format": "mkv",
        "output_dir": str(out),
    })
    assert r.status_code == 422


def test_post_jobs_rejects_non_flac_audio(client, monkeypatch, tmp_path):
    _patch_orchestration(monkeypatch)
    out = tmp_path / "out"
    r = client.post(
        "/api/jobs",
        data={
            "url": "https://x.test/a", "model": "m",
            "scale": "4", "output_format": "mkv",
            "output_dir": str(out),
        },
        files={"audio_file": ("track.mp3", b"\x00\x00", "audio/mpeg")},
    )
    assert r.status_code == 422
