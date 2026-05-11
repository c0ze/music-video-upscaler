import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport

from web.events import CompleteEvent, LogEvent
from web.server import build_app


@pytest.fixture
def app_with_models(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "realesr-general-x4v3.param").write_text("")
    (models_dir / "realesr-general-x4v3.bin").write_bytes(b"")
    return build_app(models_dir=models_dir, workdir_root=tmp_path / "jobs"), tmp_path


def test_get_thumbnail_returns_jpeg(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
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


def test_get_thumbnail_rejects_bad_kind(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    r = client.get(f"/api/jobs/{job_id}/frames/evil/000001")
    assert r.status_code == 400


def test_get_thumbnail_rejects_bad_frame_id(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    r = client.get(f"/api/jobs/{job_id}/frames/up/..%2Fstate")
    assert r.status_code in (400, 404)


def test_get_thumbnail_unknown_job(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    r = client.get("/api/jobs/no-such-job/frames/up/000001")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_events_stream_emits_subscribed_events(app_with_models):
    """Producer and consumer must share the same event loop, so use AsyncClient."""
    app, _ = app_with_models
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def producer():
            # Give the SSE handler time to subscribe.
            await asyncio.sleep(0.05)
            await mgr.publish(job_id, LogEvent(line="hello"))
            await mgr.publish(job_id, CompleteEvent(output="/tmp/x.mkv", size_bytes=1))
            await mgr.close_subscribers(job_id)

        producer_task = asyncio.create_task(producer())
        try:
            body = b""
            async with client.stream(
                "GET", f"/api/jobs/{job_id}/events", timeout=5.0
            ) as resp:
                assert resp.status_code == 200
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if b'"complete"' in body:
                        break
        finally:
            await producer_task

    text = body.decode("utf-8")
    assert "hello" in text
    assert "complete" in text


def test_events_stream_404_for_unknown_job(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    r = client.get("/api/jobs/no-such-job/events")
    assert r.status_code == 404


def test_get_output_returns_file(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, workdir = mgr.register_job(
        kind="full", url="u", model="m", scale=4, output_format="mkv",
    )
    out = workdir / "output" / "x.mkv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\x00" * 10)
    mgr.set_output(job_id, out)

    r = client.get(f"/api/jobs/{job_id}/output")
    assert r.status_code == 200
    assert len(r.content) == 10


def test_get_output_404_when_not_set(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    mgr = app.state.job_manager
    job_id, _ = mgr.register_job(kind="full", url="u", model="m", scale=4, output_format="mkv")
    r = client.get(f"/api/jobs/{job_id}/output")
    assert r.status_code == 404


def test_get_output_unknown_job(app_with_models):
    app, _ = app_with_models
    client = TestClient(app)
    r = client.get("/api/jobs/no-such-job/output")
    assert r.status_code == 404
