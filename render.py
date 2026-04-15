"""Pillow-based rendering of the "my_friend" style bubble image."""

from __future__ import annotations

from io import BytesIO
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


# ── Tunable layout constants ──────────────────────────────────────────────

CANVAS_WIDTH = 640
PADDING = 24
AVATAR_SIZE = 96
NAME_GAP = 6                # gap between nickname baseline and bubble top
BUBBLE_PAD = 18             # inner padding inside the bubble
BUBBLE_RADIUS = 20
BUBBLE_TAIL_OFFSET_Y = 28   # y offset of the little triangle tail
FONT_SIZE_TEXT = 30
FONT_SIZE_NAME = 20
LINE_SPACING = 10           # extra pixels between wrapped lines

# Colors
COLOR_NAME = (140, 140, 140)
COLOR_TEXT = (30, 30, 30)


def _parse_color(c: str, fallback: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Accept `#RRGGBB`, `#RGB`, or a named keyword. Returns an RGB tuple."""
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
    if c.lower() == "white":
        return (255, 255, 255)
    if c.lower() == "black":
        return (0, 0, 0)
    return fallback


def _wrap_cjk(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Greedy character-by-character wrap. Works for CJK where words are
    single glyphs, and degrades gracefully for Latin mixed content (will
    break inside words — acceptable for meme images)."""
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
    """Return a size×size RGBA image containing `img` cropped to a circle."""
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
    canvas_bg: str = "#EBEBEB",
    bubble_bg: str = "#FFFFFF",
) -> bytes:
    """Render a 'my_friend' style chat bubble image.

    Args:
        avatar_bytes: raw bytes of the avatar image (any Pillow-supported format).
        nickname: already-sanitized nickname string.
        text: already-sanitized body text.
        font_path: filesystem path to a CJK-capable font file.
        canvas_bg, bubble_bg: hex color strings.

    Returns:
        PNG-encoded image bytes.
    """
    canvas_rgb = _parse_color(canvas_bg, (235, 235, 235))
    bubble_rgb = _parse_color(bubble_bg, (255, 255, 255))

    font_text = ImageFont.truetype(font_path, FONT_SIZE_TEXT)
    font_name = ImageFont.truetype(font_path, FONT_SIZE_NAME)

    # Compute bubble geometry
    text_area_x0 = PADDING + AVATAR_SIZE + PADDING
    max_text_width = CANVAS_WIDTH - text_area_x0 - PADDING - BUBBLE_PAD * 2
    lines = _wrap_cjk(text, font_text, max_text_width) or [""]
    line_h = FONT_SIZE_TEXT + LINE_SPACING

    longest = max((font_text.getlength(l) for l in lines), default=0)
    bubble_w = int(min(max_text_width, longest) + BUBBLE_PAD * 2)
    bubble_w = max(bubble_w, 120)
    bubble_h = int(line_h * len(lines) + BUBBLE_PAD * 2 - LINE_SPACING)

    name_h = FONT_SIZE_NAME + NAME_GAP
    right_col_h = name_h + bubble_h
    canvas_h = PADDING * 2 + max(AVATAR_SIZE, right_col_h)

    # Canvas
    canvas = Image.new("RGB", (CANVAS_WIDTH, canvas_h), canvas_rgb)
    draw = ImageDraw.Draw(canvas)

    # Avatar
    try:
        avatar_img = Image.open(BytesIO(avatar_bytes))
    except Exception as e:
        raise ValueError(f"invalid avatar image: {e}") from e
    avatar_circle = _circular_crop(avatar_img, AVATAR_SIZE)
    canvas.paste(avatar_circle, (PADDING, PADDING), avatar_circle)

    # Nickname
    draw.text((text_area_x0, PADDING - 2), nickname,
              fill=COLOR_NAME, font=font_name)

    # Bubble
    bx0 = text_area_x0
    by0 = PADDING + name_h
    bx1 = bx0 + bubble_w
    by1 = by0 + bubble_h
    draw.rounded_rectangle((bx0, by0, bx1, by1),
                           radius=BUBBLE_RADIUS, fill=bubble_rgb)

    # Tail triangle pointing at the avatar
    tail = [
        (bx0, by0 + BUBBLE_TAIL_OFFSET_Y),
        (bx0 - 10, by0 + BUBBLE_TAIL_OFFSET_Y + 6),
        (bx0, by0 + BUBBLE_TAIL_OFFSET_Y + 12),
    ]
    draw.polygon(tail, fill=bubble_rgb)

    # Body text
    tx = bx0 + BUBBLE_PAD
    ty = by0 + BUBBLE_PAD - 2
    for i, line in enumerate(lines):
        draw.text((tx, ty + i * line_h), line, fill=COLOR_TEXT, font=font_text)

    buf = BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
