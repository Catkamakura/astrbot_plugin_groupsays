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

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ── Layout constants ──────────────────────────────────────────────────────

# Canvas colors — chosen so the bubble clearly pops from the background
CANVAS_BG_DEFAULT = (228, 232, 240)     # slightly deeper than #EAEDF4 for contrast
BUBBLE_BG_DEFAULT = (255, 255, 255)

# Avatar — sized to match real QQ proportions (was 96, way too big vs bubble)
AVATAR_X, AVATAR_Y = 16, 16
AVATAR_SIZE = 56
AVATAR_BOTTOM = AVATAR_Y + AVATAR_SIZE          # 72

# Nickname — natural gray, positioned just above the bubble
NICKNAME_X = 86                                 # aligned with bubble left edge
NICKNAME_Y = 14                                 # near top of the canvas
NICKNAME_FONT_SIZE = 16
NICKNAME_COLOR = (134, 140, 154)                # #868C9A muted gray-blue

# Speech bubble — QQ "简洁模式" aesthetic:
#   flat (no shadow / no outline), pill-shaped corners (radius ≈ height/2
#   for short text), subtle tiny tail. The whole effect is "rounded chip"
#   floating on a near-white page, with no z-depth gimmicks.
BUBBLE_X = 86                                   # 14px gap right of avatar
BUBBLE_Y = 36                                   # ~6px gap below nickname
BUBBLE_INNER_PAD = 16
# BUBBLE_RADIUS_MAX caps the radius for tall (multi-line) bubbles so they
# don't end up looking like overinflated capsules. Short bubbles use
# bubble_h / 2 → pill shape, matching the screenshot reference.
BUBBLE_RADIUS_MAX = 22
BUBBLE_TAIL_Y_OFFSET = 12                       # tail aligns near avatar's upper half
BUBBLE_TAIL_W = 5                               # tiny protrusion (was 9; QQ 简洁模式 nearly hides it)
BUBBLE_TAIL_H = 10                              # smaller vertical extent
BUBBLE_FG = (34, 34, 38)
# Floor below which a bubble would visually disappear into the page bg.
# Per-render code raises this floor up to ~bubble_height for short
# single-line texts so the bubble stays visually balanced with the avatar.
BUBBLE_MIN_W = 50
# Keep bubble at least as tall as avatar bottom (+ a hair) so they feel balanced
BUBBLE_MIN_H = (AVATAR_BOTTOM - BUBBLE_Y) + 8   # = 44

# ── QQ 简洁模式 polish ──────────────────────────────────────────────
# Both flags are OFF by default — 简洁模式 is fundamentally flat. Turning
# either ON gets you a slight z-depth / contrast boost if you want a
# more "iOS bubble" look.
SHADOW_ENABLED = False
SHADOW_COLOR = (0, 0, 0)
SHADOW_OPACITY = 26                             # 0-255; ~10% black
SHADOW_BLUR_RADIUS = 5                          # GaussianBlur radius
SHADOW_OFFSET = (0, 2)                          # (dx, dy) from bubble origin

OUTLINE_ENABLED = False
OUTLINE_COLOR = (0, 0, 0, 18)                   # ~7% black
OUTLINE_WIDTH = 1

# Body text
TEXT_FONT_SIZE = 28
TEXT_LINE_SPACING = 8
TEXT_MAX_WIDTH = 440                            # wrap width

# Canvas margins
CANVAS_RIGHT_PAD = 20
CANVAS_BOTTOM_PAD = 16


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


def _build_bubble_mask(
    width: int,
    height: int,
    radius: int,
    *,
    tail_y: int,
    tail_w: int,
    tail_h: int,
) -> Image.Image:
    """Return an alpha mask (mode='L') with the QQ-style bubble silhouette.

    The silhouette = rounded-rectangle ∪ tail. Tail is a small leaf-like
    shape on the LEFT side, centered vertically at ``tail_y``, protruding
    ``tail_w`` pixels outward. Using a mask keeps anti-aliasing consistent
    between body and tail and lets us blur it cleanly for the drop shadow.

    Output is sized ``(width + tail_w, height)`` so the tail has room.
    """
    canvas_w = width + tail_w
    canvas_h = height
    mask = Image.new("L", (canvas_w, canvas_h), 0)
    md = ImageDraw.Draw(mask)
    # Bubble body — shifted right by tail_w so the tail can protrude left
    md.rounded_rectangle(
        (tail_w, 0, tail_w + width - 1, height - 1),
        radius=radius,
        fill=255,
    )
    # Tail — a curved "ear" instead of a sharp triangle. Approximated with
    # an ellipse trimmed by overlap with the bubble body.
    # Anchor: left edge of the bubble body.
    tail_top = tail_y - tail_h // 2
    tail_bot = tail_y + tail_h // 2
    # Outer ellipse extends LEFT of the body, into the canvas's leftmost
    # tail_w pixels. We make it wider than tail_w so its rightmost edge
    # blends into the body.
    md.ellipse(
        (0, tail_top, tail_w * 2, tail_bot),
        fill=255,
    )
    # Top inner corner: a small notch to keep the tail from looking
    # like a perfect circle pasted on the side. Carve out a rounded
    # bite where the tail meets the body's top edge.
    md.ellipse(
        (
            tail_w - 2,
            tail_top - tail_h // 3,
            tail_w + 4,
            tail_top + tail_h // 3,
        ),
        fill=0,
    )
    return mask


def _composite_bubble(
    canvas: Image.Image,
    *,
    body_xy: Tuple[int, int],
    body_wh: Tuple[int, int],
    radius: int,
    fill: Tuple[int, int, int],
    tail_y_offset: int,
    tail_w: int,
    tail_h: int,
) -> None:
    """Paint a QQ-style bubble (body + curved tail + drop shadow + outline)
    onto ``canvas`` in place.

    Order of operations:
      1. Build alpha-mask silhouette (rounded-rect ∪ ear-shaped tail).
      2. Render drop shadow: blur the mask, paint as low-alpha black,
         offset by SHADOW_OFFSET.
      3. Render body: paint solid fill via the mask.
      4. Render outline: stroke the mask boundary with low-alpha black.
    """
    bx, by = body_xy
    bw, bh = body_wh
    mask = _build_bubble_mask(
        bw, bh, radius,
        tail_y=tail_y_offset,
        tail_w=tail_w, tail_h=tail_h,
    )
    # Place the mask so the body is at (bx, by) and the tail extends
    # tail_w pixels to the LEFT of bx.
    paste_x = bx - tail_w
    paste_y = by

    # 1. Drop shadow (paint blurred mask as low-alpha black behind body).
    if SHADOW_ENABLED:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        # Build a same-size mask shifted into canvas coordinates.
        shadow_mask = Image.new("L", canvas.size, 0)
        shadow_mask.paste(mask, (paste_x + SHADOW_OFFSET[0], paste_y + SHADOW_OFFSET[1]))
        shadow_mask = shadow_mask.filter(
            ImageFilter.GaussianBlur(radius=SHADOW_BLUR_RADIUS)
        )
        shadow_color_layer = Image.new(
            "RGBA", canvas.size,
            (*SHADOW_COLOR, SHADOW_OPACITY),
        )
        shadow_layer.paste(shadow_color_layer, (0, 0), shadow_mask)
        # Composite shadow under the rest. canvas is RGB; convert temp.
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.alpha_composite(shadow_layer)
        # Write back to original canvas as RGB.
        canvas.paste(canvas_rgba.convert("RGB"))

    # 2. Body — solid fill via mask.
    body_layer = Image.new("RGBA", mask.size, (*fill, 255))
    canvas.paste(body_layer, (paste_x, paste_y), mask)

    # 3. Outline — stroke the mask boundary at low opacity. Subtle but
    # makes the bubble pop on light backgrounds.
    if OUTLINE_ENABLED and OUTLINE_COLOR[3] > 0:
        # Edge = mask - eroded(mask), approximated by subtracting a
        # 1px-blurred copy. Cheap but works.
        from PIL import ImageChops
        eroded = mask.filter(ImageFilter.MinFilter(3))
        edge = ImageChops.subtract(mask, eroded)
        outline_layer = Image.new("RGBA", mask.size, OUTLINE_COLOR)
        canvas_rgba = canvas.convert("RGBA")
        outline_paste = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        outline_paste.paste(outline_layer, (paste_x, paste_y), edge)
        canvas_rgba.alpha_composite(outline_paste)
        canvas.paste(canvas_rgba.convert("RGB"))


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
    bubble_h = max(text_h + BUBBLE_INNER_PAD * 2, BUBBLE_MIN_H)
    # Width: snug to the text, but never below MIN_W (so a single dot or
    # whitespace doesn't render as a sliver). For single-line short texts
    # we additionally floor at bubble_h so the bubble stays roughly square
    # — visually consistent with how QQ actually renders one-character
    # replies. Multi-line texts skip this floor (they're already wide
    # enough to look natural).
    is_short_singleline = len(lines) == 1 and len(lines[0]) <= 6
    width_floor = BUBBLE_MIN_W
    if is_short_singleline:
        width_floor = max(width_floor, bubble_h)
    bubble_w = max(text_w + BUBBLE_INNER_PAD * 2, width_floor)

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

    # ── 7. Bubble (QQ 简洁模式: pill-rounded, flat, tiny tail) ──
    bx0, by0 = BUBBLE_X, BUBBLE_Y
    bx1 = bx0 + int(bubble_w)
    by1 = by0 + int(bubble_h)
    # Dynamic radius: short bubbles → bubble_h/2 (true pill shape, matches
    # QQ 简洁模式 reference); tall bubbles → cap at BUBBLE_RADIUS_MAX so a
    # multi-line block isn't an overinflated capsule.
    effective_radius = min(int(bubble_h) // 2, BUBBLE_RADIUS_MAX)
    _composite_bubble(
        canvas,
        body_xy=(bx0, by0),
        body_wh=(int(bubble_w), int(bubble_h)),
        radius=effective_radius,
        fill=bubble_rgb,
        tail_y_offset=BUBBLE_TAIL_Y_OFFSET,
        tail_w=BUBBLE_TAIL_W,
        tail_h=BUBBLE_TAIL_H,
    )
    # ImageDraw cache — _composite_bubble may have rebuilt the canvas
    # via .paste()/.convert() round-trips, so refresh `draw`.
    draw = ImageDraw.Draw(canvas)

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
