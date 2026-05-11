import re
import time
from pathlib import Path

import pytest

from web.workdir import WorkdirManager, default_root, default_output_dir


def test_default_root_is_under_user_cache():
    p = default_root()
    assert "music-video-upscaler" in p.parts
    assert p.name == "jobs"


def test_default_output_dir_returns_existing_kind_per_os():
    p = default_output_dir()
    assert p.name == "MusicVideoUpscaled"


def test_create_job_returns_id_and_dir(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert re.match(r"^\d{8}-\d{6}-[a-z0-9]{6}$", job_id)
    assert workdir.is_dir()
    assert workdir.parent == tmp_path
    assert (workdir / "source").is_dir()
    assert (workdir / "thumbs").is_dir()
    assert (workdir / "output").is_dir()


def test_state_path_returns_state_json(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert mgr.state_path(job_id) == workdir / "state.json"


def test_log_path_returns_log_txt(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    job_id, workdir = mgr.create_job()
    assert mgr.log_path(job_id) == workdir / "log.txt"


def test_get_workdir_raises_when_missing(tmp_path):
    mgr = WorkdirManager(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.get_workdir("does-not-exist")


def test_cleanup_keeps_recent_n_and_non_terminal(tmp_path):
    import json

    mgr = WorkdirManager(root=tmp_path, keep_recent=2, max_age_seconds=1)
    ids = []
    for _ in range(5):
        jid, wd = mgr.create_job()
        # Mark as complete (terminal)
        (wd / "state.json").write_text(json.dumps({"state": "complete"}))
        ids.append(jid)
        time.sleep(0.01)
    # Bend mtime backwards on three oldest to trigger cleanup
    for jid in ids[:3]:
        wd = mgr.get_workdir(jid)
        old = time.time() - 10
        for p in wd.rglob("*"):
            try:
                import os
                os.utime(p, (old, old))
            except OSError:
                pass
        import os
        os.utime(wd, (old, old))

    mgr.cleanup()

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert ids[-1] in remaining
    assert ids[-2] in remaining
    assert ids[0] not in remaining


def test_cleanup_keeps_non_terminal_even_when_old(tmp_path):
    import json
    import os

    mgr = WorkdirManager(root=tmp_path, keep_recent=0, max_age_seconds=1)
    jid, wd = mgr.create_job()
    (wd / "state.json").write_text(json.dumps({"state": "upscaling"}))
    old = time.time() - 100
    os.utime(wd, (old, old))

    mgr.cleanup()
    assert wd.is_dir()
