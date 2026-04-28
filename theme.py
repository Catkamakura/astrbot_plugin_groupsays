"""Theme system: 9-slice bubble themes loaded from disk.

A theme is a directory containing:

    <theme_dir>/
    ├── manifest.json
    └── body.png            (or body.9.png — Android 9-patch)

``manifest.json`` schema (all paths relative to the theme dir)::

    {
      "name": "Classic",
      "body": "body.png",
      "padding_9slice":   [top, left, bottom, right],
      "padding_content":  [top, left, bottom, right],
      "text_color":       "#000000",
      "min_size":         [w, h]
    }

When the body file is a ``.9.png`` (Android 9-patch), the
``padding_9slice`` and ``padding_content`` fields can be omitted —
they're parsed from the marker pixels on the image's 1-px border.

Resolution order for theme lookup:
    1. ``<plugin_data>/themes/<name>/``    — user themes (writable)
    2. ``<plugin>/themes/<name>/``         — bundled themes (read-only)

Both directories are scanned at load time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image


# ── Theme model ─────────────────────────────────────────────────────


@dataclass
class Theme:
    """A loaded theme — image + metadata, ready to 9-slice scale."""
    name: str
    body_image: Image.Image
    padding_9slice: Tuple[int, int, int, int]   # (top, left, bottom, right)
    padding_content: Tuple[int, int, int, int]
    text_color: Tuple[int, int, int]
    min_size: Tuple[int, int] = (0, 0)
    source_dir: Optional[Path] = None

    @property
    def src_size(self) -> Tuple[int, int]:
        return self.body_image.size

    @classmethod
    def load(cls, theme_dir: Path) -> "Theme":
        manifest_path = theme_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"theme manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        body_name = manifest.get("body", "body.png")
        body_path = theme_dir / body_name
        if not body_path.exists():
            raise FileNotFoundError(f"theme body image not found: {body_path}")

        img = Image.open(body_path).convert("RGBA")

        if body_name.endswith(".9.png"):
            # Android 9-patch — read markers, strip border
            slice_pad, content_pad = parse_9patch_markers(img)
            img = img.crop((1, 1, img.width - 1, img.height - 1))
        else:
            if "padding_9slice" not in manifest:
                raise ValueError(
                    f"theme {theme_dir.name}: padding_9slice required when body is plain PNG"
                )
            slice_pad = tuple(manifest["padding_9slice"])  # type: ignore
            content_pad = tuple(manifest.get("padding_content", slice_pad))  # type: ignore

        text_color = _hex_to_rgb(manifest.get("text_color", "#000000"))
        min_size = tuple(manifest.get("min_size", [0, 0]))  # type: ignore

        return cls(
            name=manifest.get("name", theme_dir.name),
            body_image=img,
            padding_9slice=slice_pad,
            padding_content=content_pad,
            text_color=text_color,
            min_size=min_size,
            source_dir=theme_dir,
        )


# ── Discovery ───────────────────────────────────────────────────────


def discover_themes(*search_dirs: Path) -> "dict[str, Path]":
    """Return ``{theme_name: theme_dir}`` for every valid theme found.

    A directory is treated as a theme if it contains both ``manifest.json``
    and the body image referenced therein. First-seen wins (so user themes
    in ``plugin_data/themes`` shadow bundled themes with the same name).
    """
    found: dict[str, Path] = {}
    for root in search_dirs:
        if not root or not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith("_") or child.name.startswith("."):
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.exists():
                continue
            if child.name not in found:
                found[child.name] = child
    return found


def load_theme_or_none(name: str, search_dirs: List[Path]) -> Optional[Theme]:
    """Best-effort theme load. Returns None if name not found / load fails."""
    if not name:
        return None
    themes = discover_themes(*search_dirs)
    theme_dir = themes.get(name)
    if not theme_dir:
        return None
    try:
        return Theme.load(theme_dir)
    except Exception:
        return None


# ── 9-slice scaling ─────────────────────────────────────────────────


def render_9slice(
    body: Image.Image,
    target_size: Tuple[int, int],
    padding_9slice: Tuple[int, int, int, int],
) -> Image.Image:
    """Scale ``body`` to ``target_size`` using 9-slice scaling.

    Corners (size = ``padding_9slice``) stay pixel-identical. The 4 edges
    stretch in one axis only; the center stretches in both. Output is
    always RGBA.

    Raises ValueError if the target is smaller than the corners or the
    padding exceeds the source.
    """
    src_w, src_h = body.size
    tgt_w, tgt_h = target_size
    pt, pl, pb, pr = padding_9slice

    if pt + pb >= src_h or pl + pr >= src_w:
        raise ValueError(
            f"9-slice padding {padding_9slice} leaves no center area "
            f"(source size {body.size})"
        )
    tgt_w = max(tgt_w, pl + pr)
    tgt_h = max(tgt_h, pt + pb)

    src_cw = src_w - pl - pr     # source center width
    src_ch = src_h - pt - pb
    tgt_cw = tgt_w - pl - pr
    tgt_ch = tgt_h - pt - pb

    out = Image.new("RGBA", (tgt_w, tgt_h), (0, 0, 0, 0))

    # 4 corners (no scaling)
    out.paste(body.crop((0, 0, pl, pt)), (0, 0))
    out.paste(body.crop((src_w - pr, 0, src_w, pt)), (tgt_w - pr, 0))
    out.paste(body.crop((0, src_h - pb, pl, src_h)), (0, tgt_h - pb))
    out.paste(body.crop((src_w - pr, src_h - pb, src_w, src_h)), (tgt_w - pr, tgt_h - pb))

    # 4 edges
    if tgt_cw > 0:
        top_e = body.crop((pl, 0, src_w - pr, pt))
        out.paste(top_e.resize((tgt_cw, pt), Image.LANCZOS), (pl, 0))
        bot_e = body.crop((pl, src_h - pb, src_w - pr, src_h))
        out.paste(bot_e.resize((tgt_cw, pb), Image.LANCZOS), (pl, tgt_h - pb))
    if tgt_ch > 0:
        left_e = body.crop((0, pt, pl, src_h - pb))
        out.paste(left_e.resize((pl, tgt_ch), Image.LANCZOS), (0, pt))
        right_e = body.crop((src_w - pr, pt, src_w, src_h - pb))
        out.paste(right_e.resize((pr, tgt_ch), Image.LANCZOS), (tgt_w - pr, pt))
    if tgt_cw > 0 and tgt_ch > 0:
        center = body.crop((pl, pt, src_w - pr, src_h - pb))
        out.paste(center.resize((tgt_cw, tgt_ch), Image.LANCZOS), (pl, pt))

    return out


# ── Android 9-patch marker parsing ──────────────────────────────────


def parse_9patch_markers(
    img: Image.Image,
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Parse marker pixels on a ``.9.png`` to derive padding.

    Android 9-patch convention (with a 1-px transparent border that
    has black markers):

      - **Top edge** (y=0): contiguous black pixels = stretchable
        horizontal region. Anything outside that run is a fixed corner.
      - **Left edge** (x=0): black pixels = stretchable vertical region.
      - **Bottom edge** (y=h-1, optional): black pixels = content x-bounds.
      - **Right edge** (x=w-1, optional): black pixels = content y-bounds.

    Returns ``(padding_9slice, padding_content)`` where each is a 4-tuple
    of ``(top, left, bottom, right)`` measured in the **stripped image's**
    coordinate system (i.e. after the 1-px border is removed by the caller).
    """
    px = img.load()
    w, h = img.size

    def first_run(pixels: List) -> Optional[Tuple[int, int]]:
        start = None
        for i, p in enumerate(pixels):
            if _is_marker(p):
                if start is None:
                    start = i
            elif start is not None:
                return (start, i)
        if start is not None:
            return (start, len(pixels))
        return None

    top_run = first_run([px[x, 0] for x in range(w)])
    left_run = first_run([px[0, y] for y in range(h)])
    bot_run = first_run([px[x, h - 1] for x in range(w)])
    right_run = first_run([px[w - 1, y] for y in range(h)])

    if top_run is None or left_run is None:
        raise ValueError(
            "9-patch image is missing stretch markers on top and/or left edge"
        )

    inner_w = w - 2  # post-strip width
    inner_h = h - 2

    pl = max(0, top_run[0] - 1)
    pr = max(0, inner_w - (top_run[1] - 1))
    pt = max(0, left_run[0] - 1)
    pb = max(0, inner_h - (left_run[1] - 1))

    # Fall back to slice padding if content markers absent
    if bot_run is not None:
        cl = max(0, bot_run[0] - 1)
        cr = max(0, inner_w - (bot_run[1] - 1))
    else:
        cl, cr = pl, pr
    if right_run is not None:
        ct = max(0, right_run[0] - 1)
        cb = max(0, inner_h - (right_run[1] - 1))
    else:
        ct, cb = pt, pb

    return (pt, pl, pb, pr), (ct, cl, cb, cr)


# ── Heuristic 9-slice detection (for plain PNGs) ────────────────────


def heuristic_9slice(
    img: Image.Image,
    *,
    uniformity_threshold: int = 6,
) -> Tuple[int, int, int, int]:
    """Guess 9-slice corner sizes from a plain bubble PNG.

    Strategy: scan pixel rows / columns from each edge inward; the first
    row/column whose middle band (between the corners) is "uniform enough"
    marks the start of the stretchable area. ``uniformity_threshold`` is
    the max per-channel pixel-value variance allowed in that band.

    Not perfect — themes with gradients in the stretch area or noisy
    interiors will fool the detector. Manifest can override.
    """
    arr_img = img.convert("RGBA")
    w, h = arr_img.size
    px = arr_img.load()

    def row_uniform(y: int, x_start: int, x_end: int) -> bool:
        ref = px[x_start, y]
        for x in range(x_start + 1, x_end):
            p = px[x, y]
            if any(abs(p[c] - ref[c]) > uniformity_threshold for c in range(4)):
                return False
        return True

    def col_uniform(x: int, y_start: int, y_end: int) -> bool:
        ref = px[x, y_start]
        for y in range(y_start + 1, y_end):
            p = px[x, y]
            if any(abs(p[c] - ref[c]) > uniformity_threshold for c in range(4)):
                return False
        return True

    # We sample the middle band (1/4 to 3/4 of the orthogonal axis)
    # to skip the corner curvature when checking uniformity.
    x_lo, x_hi = w // 4, 3 * w // 4
    y_lo, y_hi = h // 4, 3 * h // 4

    pt = 0
    for y in range(h // 2):
        if row_uniform(y, x_lo, x_hi):
            pt = y
            break
    pb = 0
    for y in range(h - 1, h // 2, -1):
        if row_uniform(y, x_lo, x_hi):
            pb = h - 1 - y
            break
    pl = 0
    for x in range(w // 2):
        if col_uniform(x, y_lo, y_hi):
            pl = x
            break
    pr = 0
    for x in range(w - 1, w // 2, -1):
        if col_uniform(x, y_lo, y_hi):
            pr = w - 1 - x
            break

    # Sane minimum
    pt = max(pt, 4)
    pl = max(pl, 4)
    pb = max(pb, 4)
    pr = max(pr, 4)
    return (pt, pl, pb, pr)


# ── Helpers ─────────────────────────────────────────────────────────


def _hex_to_rgb(s: str) -> Tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _is_marker(px) -> bool:
    """A 9-patch marker pixel is solid opaque black (per Android spec)."""
    if not isinstance(px, tuple):
        return False
    if len(px) >= 4 and px[3] < 200:
        return False
    return px[0] < 16 and px[1] < 16 and px[2] < 16
