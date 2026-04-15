"""Pillow-based rendering of the "my_friend" style bubble image.

Mimics a natural QQ group-chat screenshot:
  - Light gray-blue page background
  - Avatar as a circle, top-left
  - Nickname as plain muted text, just above the bubble
  - White speech bubble with a small tail pointing at the avatar
  - Body text centered (both axes) inside the bubble
"""

from __future__ import annotations

from io import BytesIO
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


# ── Layout constants ──────────────────────────────────────────────────────

# Canvas colors — chosen so the bubble clearly pops from the background
CANVAS_BG_DEFAULT = (228, 232, 240)     # slightly deeper than #EAEDF4 for contrast
BUBBLE_BG_DEFAULT = (255, 255, 255)

# Avatar
AVATAR_X, AVATAR_Y = 20, 22
AVATAR_SIZE = 96
AVATAR_BOTTOM = AVATAR_Y + AVATAR_SIZE          # 118

# Nickname — natural gray, positioned just above the bubble
NICKNAME_X = 130                                # aligned with bubble left edge
NICKNAME_Y = 18                                 # near top of the canvas
NICKNAME_FONT_SIZE = 22
NICKNAME_COLOR = (134, 140, 154)                # #868C9A muted gray-blue

# Speech bubble
BUBBLE_X = 130                                  # 14px gap right of avatar
BUBBLE_Y = 56                                   # leaves ~16px gap below nickname
BUBBLE_INNER_PAD = 20
BUBBLE_RADIUS = 22
BUBBLE_TAIL_Y_OFFSET = 22                       # tail aligns near avatar's upper half
BUBBLE_FG = (34, 34, 38)
BUBBLE_MIN_W = 170
# Keep bubble at least as tall as avatar bottom (+ a hair) so they feel balanced
BUBBLE_MIN_H = (AVATAR_BOTTOM - BUBBLE_Y) + 12  # = 74

# Body text
TEXT_FONT_SIZE = 32
TEXT_LINE_SPACING = 10
TEXT_MAX_WIDTH = 500                            # wrap width

# Canvas margins
CANVAS_RIGHT_PAD = 28
CANVAS_BOTTOM_PAD = 24


def _parse_color(c: str, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    if not c:
        return fallback
    c = c.strip()
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) == 6:
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return fallback
    lowered = c.lower()
    if lowered == "white":
        return (255, 255, 255)
    if lowered == "black":
        return (0, 0, 0)
    return fallback


def _wrap_cjk(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Greedy per-character wrapping — atomic CJK glyphs make this safe."""
    lines: List[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
            continue
        cur = ""
        cur_w = 0.0
        for ch in raw_line:
            w = font.getlength(ch)
            if cur_w + w > max_width and cur:
                lines.append(cur)
                cur, cur_w = ch, w
            else:
                cur += ch
                cur_w += w
        if cur:
            lines.append(cur)
    return lines


def _circular_crop(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def render_my_friend(
    avatar_bytes: bytes,
    nickname: str,
    text: str,
    font_path: str,
    *,
    canvas_bg: str = "#E4E8F0",
    bubble_bg: str = "#FFFFFF",
) -> bytes:
    """Render a group-chat 'my_friend' style image.

    Args:
        avatar_bytes: raw avatar image bytes.
        nickname: already-sanitized nickname.
        text: already-sanitized body text.
        font_path: path to a CJK-capable font file.
        canvas_bg: page background (defaults to soft QQ-chat gray-blue).
        bubble_bg: bubble fill color (defaults to white).

    Returns:
        PNG-encoded bytes.
    """
    canvas_rgb = _parse_color(canvas_bg, CANVAS_BG_DEFAULT)
    bubble_rgb = _parse_color(bubble_bg, BUBBLE_BG_DEFAULT)

    font_text = ImageFont.truetype(font_path, TEXT_FONT_SIZE)
    font_name = ImageFont.truetype(font_path, NICKNAME_FONT_SIZE)

    # ── 1. Wrap & measure body text ──────────────────────────────────
    lines = _wrap_cjk(text, font_text, TEXT_MAX_WIDTH) or [""]
    wrapped = "\n".join(lines)

    _probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tb = _probe.multiline_textbbox(
        (0, 0), wrapped, font=font_text, spacing=TEXT_LINE_SPACING
    )
    text_w = tb[2] - tb[0]
    text_h = tb[3] - tb[1]

    # ── 2. Measure nickname ──────────────────────────────────────────
    name_display = nickname or "(匿名)"
    name_w = int(font_name.getlength(name_display))

    # ── 3. Bubble dimensions ─────────────────────────────────────────
    bubble_w = max(
        text_w + BUBBLE_INNER_PAD * 2,
        BUBBLE_MIN_W,
    )
    bubble_h = max(text_h + BUBBLE_INNER_PAD * 2, BUBBLE_MIN_H)

    # ── 4. Canvas dimensions (adaptive) ─────────────────────────────
    # Width must accommodate the wider of bubble or nickname
    right_col_w = max(int(bubble_w), name_w)
    canvas_w = BUBBLE_X + right_col_w + CANVAS_RIGHT_PAD
    canvas_h = BUBBLE_Y + int(bubble_h) + CANVAS_BOTTOM_PAD

    canvas = Image.new("RGB", (canvas_w, canvas_h), canvas_rgb)
    draw = ImageDraw.Draw(canvas)

    # ── 5. Avatar ────────────────────────────────────────────────────
    try:
        avatar_img = Image.open(BytesIO(avatar_bytes))
    except Exception as e:
        raise ValueError(f"invalid avatar image: {e}") from e
    avatar_circle = _circular_crop(avatar_img, AVATAR_SIZE)
    canvas.paste(avatar_circle, (AVATAR_X, AVATAR_Y), avatar_circle)

    # ── 6. Nickname (plain gray text, just above the bubble) ─────────
    draw.text(
        (NICKNAME_X, NICKNAME_Y),
        name_display,
        fill=NICKNAME_COLOR,
        font=font_name,
    )

    # ── 7. Bubble ────────────────────────────────────────────────────
    bx0, by0 = BUBBLE_X, BUBBLE_Y
    bx1 = bx0 + int(bubble_w)
    by1 = by0 + int(bubble_h)
    draw.rounded_rectangle(
        (bx0, by0, bx1, by1), radius=BUBBLE_RADIUS, fill=bubble_rgb
    )

    # Tail: left-pointing triangle near top of bubble, aimed at avatar
    tail_y = by0 + BUBBLE_TAIL_Y_OFFSET
    draw.polygon(
        [(bx0, tail_y), (bx0 - 10, tail_y + 7), (bx0, tail_y + 14)],
        fill=bubble_rgb,
    )

    # ── 8. Body text — centered in bubble, bearing-compensated ───────
    text_cx = bx0 + (int(bubble_w) - text_w) // 2 - tb[0]
    text_cy = by0 + (int(bubble_h) - text_h) // 2 - tb[1]
    draw.multiline_text(
        (text_cx, text_cy),
        wrapped,
        fill=BUBBLE_FG,
        font=font_text,
        spacing=TEXT_LINE_SPACING,
        align="left",
    )

    buf = BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
