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
