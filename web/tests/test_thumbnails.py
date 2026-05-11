from pathlib import Path

import pytest

from web.thumbnails import ThumbnailGenerator


def _make_png(path: Path, width: int = 1920, height: int = 1080) -> None:
    from PIL import Image
    Image.new("RGB", (width, height), (10, 20, 30)).save(path, "PNG")


@pytest.mark.asyncio
async def test_generate_with_pillow_produces_360px_jpeg(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator()
    await gen.generate(src, dst, width=360)

    from PIL import Image
    with Image.open(dst) as im:
        assert im.format == "JPEG"
        assert im.size[0] == 360
        assert im.size[1] == 202  # 1080 * (360/1920)


@pytest.mark.asyncio
async def test_generate_idempotent_when_dst_exists(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator()
    await gen.generate(src, dst)
    mtime1 = dst.stat().st_mtime
    await gen.generate(src, dst)
    assert dst.stat().st_mtime == mtime1


@pytest.mark.asyncio
async def test_ffmpeg_fallback_when_pillow_disabled(tmp_path):
    src = tmp_path / "src.png"
    dst = tmp_path / "thumb.jpg"
    _make_png(src)

    gen = ThumbnailGenerator(prefer_pillow=False)
    await gen.generate(src, dst, width=360)
    assert dst.is_file()
    assert dst.stat().st_size > 0
