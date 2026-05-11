"""Job state machine."""
from __future__ import annotations

from enum import Enum
from typing import Set


class JobState(str, Enum):
    CREATED = "created"
    DOWNLOADING = "downloading"
    PREPARING = "preparing"
    EXTRACTING = "extracting"
    UPSCALING = "upscaling"
    MUXING = "muxing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in _TERMINAL


class JobKind(str, Enum):
    FULL = "full"
    PREVIEW = "preview"


_TERMINAL: Set[JobState] = {JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED}

_FORWARD_CHAIN = [
    JobState.CREATED,
    JobState.DOWNLOADING,
    JobState.PREPARING,
    JobState.EXTRACTING,
    JobState.UPSCALING,
    JobState.MUXING,
    JobState.COMPLETE,
]
_FORWARD_INDEX = {s: i for i, s in enumerate(_FORWARD_CHAIN)}
_ACTIVE = set(_FORWARD_CHAIN[1:-1])  # DOWNLOADING..MUXING


def can_transition(src: JobState, dst: JobState) -> bool:
    if src.is_terminal():
        return False
    if dst in (JobState.FAILED, JobState.CANCELLED):
        return src in _ACTIVE or src == JobState.CREATED
    if src in _FORWARD_INDEX and dst in _FORWARD_INDEX:
        return _FORWARD_INDEX[dst] == _FORWARD_INDEX[src] + 1
    return False


class IllegalTransition(RuntimeError):
    def __init__(self, src: JobState, dst: JobState):
        super().__init__(f"Illegal job state transition: {src.name} -> {dst.name}")
        self.src = src
        self.dst = dst
