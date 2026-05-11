"""yt-dlp probe + scale recommendation."""
from __future__ import annotations


def recommended_scale(height: int) -> int:
    """Return 2 for 1080p+, 4 for everything below (or unknown)."""
    if height >= 1080:
        return 2
    return 4
