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
