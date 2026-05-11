import pytest

from web.state import IllegalTransition, JobKind, JobState, can_transition


def test_jobstate_has_expected_members():
    expected = {
        "CREATED", "DOWNLOADING", "PREPARING", "EXTRACTING",
        "UPSCALING", "MUXING", "COMPLETE", "FAILED", "CANCELLED",
    }
    assert {s.name for s in JobState} == expected


def test_jobkind_has_full_and_preview():
    assert {k.name for k in JobKind} == {"FULL", "PREVIEW"}


def test_terminal_states_are_terminal():
    for s in [JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED]:
        assert s.is_terminal()


def test_active_states_are_not_terminal():
    for s in [JobState.CREATED, JobState.DOWNLOADING, JobState.PREPARING,
              JobState.EXTRACTING, JobState.UPSCALING, JobState.MUXING]:
        assert not s.is_terminal()


def test_can_transition_full_pipeline():
    chain = [
        JobState.CREATED, JobState.DOWNLOADING, JobState.PREPARING,
        JobState.EXTRACTING, JobState.UPSCALING, JobState.MUXING,
        JobState.COMPLETE,
    ]
    for src, dst in zip(chain, chain[1:]):
        assert can_transition(src, dst), f"{src} -> {dst} should be allowed"


def test_can_transition_to_failed_or_cancelled_from_any_active_state():
    for src in [JobState.DOWNLOADING, JobState.PREPARING, JobState.EXTRACTING,
                JobState.UPSCALING, JobState.MUXING]:
        assert can_transition(src, JobState.FAILED)
        assert can_transition(src, JobState.CANCELLED)


def test_cannot_transition_from_terminal_state():
    for src in [JobState.COMPLETE, JobState.FAILED, JobState.CANCELLED]:
        for dst in JobState:
            assert not can_transition(src, dst)


def test_cannot_skip_active_states():
    assert not can_transition(JobState.DOWNLOADING, JobState.UPSCALING)
    assert not can_transition(JobState.CREATED, JobState.MUXING)


def test_illegal_transition_is_an_exception():
    err = IllegalTransition(JobState.COMPLETE, JobState.UPSCALING)
    assert "COMPLETE" in str(err) and "UPSCALING" in str(err)
