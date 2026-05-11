from pathlib import Path

from web.models import ModelInfo, list_models, DEFAULT_MODEL


def _touch_pair(dir_: Path, name: str) -> None:
    (dir_ / f"{name}.param").write_text("")
    (dir_ / f"{name}.bin").write_bytes(b"")


def test_list_models_returns_only_complete_pairs(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")
    (tmp_path / "orphan.param").write_text("")  # missing .bin

    models = list_models(tmp_path)
    names = {m.name for m in models}

    assert names == {"realesr-general-x4v3", "realesrgan-x4plus"}


def test_list_models_marks_default(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")

    models = list_models(tmp_path)
    defaults = [m for m in models if m.default]

    assert len(defaults) == 1
    assert defaults[0].name == DEFAULT_MODEL


def test_list_models_returns_empty_for_empty_dir(tmp_path):
    assert list_models(tmp_path) == []


def test_list_models_returns_empty_when_dir_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert list_models(missing) == []


def test_list_models_attaches_known_hints(tmp_path):
    _touch_pair(tmp_path, "realesr-general-x4v3")
    _touch_pair(tmp_path, "realesr-general-wdn-x4v3")
    _touch_pair(tmp_path, "realesrgan-x4plus")
    _touch_pair(tmp_path, "weird-custom-model")

    models = {m.name: m for m in list_models(tmp_path)}

    assert "compressed YouTube" in models["realesr-general-x4v3"].hint
    assert "denoise" in models["realesr-general-wdn-x4v3"].hint.lower()
    assert "clean" in models["realesrgan-x4plus"].hint.lower()
    assert models["weird-custom-model"].hint == ""


def test_modelinfo_is_a_dataclass():
    m = ModelInfo(name="x", default=False, hint="y")
    assert m.name == "x"
    assert m.default is False
    assert m.hint == "y"
