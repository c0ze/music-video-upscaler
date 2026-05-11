"""Smoke test: the package imports and exposes a version."""
import web


def test_version_exposed():
    assert isinstance(web.__version__, str)
    assert web.__version__
