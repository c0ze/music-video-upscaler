import pytest

from web.probe import recommended_scale


@pytest.mark.parametrize(
    "height,expected",
    [
        (240, 4),
        (360, 4),
        (480, 4),
        (720, 4),
        (1079, 4),
        (1080, 2),
        (1440, 2),
        (2160, 2),
    ],
)
def test_recommended_scale(height, expected):
    assert recommended_scale(height) == expected


def test_recommended_scale_zero_or_negative_returns_4():
    assert recommended_scale(0) == 4
    assert recommended_scale(-1) == 4
