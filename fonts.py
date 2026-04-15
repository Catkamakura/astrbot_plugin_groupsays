"""Font discovery and first-run auto-download.

Resolution priority:
    1. Any font already present in ``<plugin>/fonts/``
    2. Common system font paths (Debian/Ubuntu, macOS, Windows)
    3. Download Source Han Sans CN Regular from GitHub (~11 MB)

The resolved path is cached in-process so subsequent calls are free.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from astrbot.api import logger


PLUGIN_DIR = Path(__file__).parent
FONTS_DIR = PLUGIN_DIR / "fonts"
DOWNLOADED_FONT = FONTS_DIR / "SourceHanSansCN-Regular.otf"

# Stable raw URL on Adobe's official font repo.
FONT_URL = (
    "https://github.com/adobe-fonts/source-han-sans/raw/release/"
    "SubsetOTF/CN/SourceHanSansCN-Regular.otf"
)

# System font candidates, ordered by quality for CJK.
_SYSTEM_CANDIDATES = [
    # Linux / Debian-family (needs fonts-noto-cjk or fonts-wqy-microhei)
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    # macOS
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    # Windows
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
]


_cached_path: Optional[str] = None
_lock = asyncio.Lock()


async def ensure_font() -> str:
    """Return a filesystem path to a usable CJK font."""
    global _cached_path
    if _cached_path:
        return _cached_path

    async with _lock:
        if _cached_path:
            return _cached_path

        # 1. Any user-provided font in the plugin's fonts/ dir
        if FONTS_DIR.exists():
            for candidate in sorted(FONTS_DIR.iterdir()):
                if candidate.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    logger.info(f"[groupsays] using font: {candidate}")
                    _cached_path = str(candidate)
                    return _cached_path

        # 2. System candidates
        for p in _SYSTEM_CANDIDATES:
            if p.exists():
                logger.info(f"[groupsays] using system font: {p}")
                _cached_path = str(p)
                return _cached_path

        # 3. Download fallback
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"[groupsays] downloading font from {FONT_URL}")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(FONT_URL)
            resp.raise_for_status()
            DOWNLOADED_FONT.write_bytes(resp.content)
        mb = len(resp.content) / 1_000_000
        logger.info(f"[groupsays] font saved to {DOWNLOADED_FONT} ({mb:.1f} MB)")
        _cached_path = str(DOWNLOADED_FONT)
        return _cached_path
