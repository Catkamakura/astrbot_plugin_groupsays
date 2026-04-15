"""Message parsing & string sanitization helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import Tuple, Optional

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Plain


# ── Unicode ranges ────────────────────────────────────────────────────────

# Coarse emoji regex covering most Unicode emoji blocks.
# Not perfect (emoji sequences with ZWJ / skin-tone modifiers may leave
# fragments) but good enough for nickname sanitization.
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # Emoticons
    "\U0001F300-\U0001F5FF"   # Symbols & Pictographs
    "\U0001F680-\U0001F6FF"   # Transport & Map
    "\U0001F700-\U0001F77F"   # Alchemical
    "\U0001F780-\U0001F7FF"   # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"   # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"   # Supplemental Symbols & Pictographs
    "\U0001FA00-\U0001FA6F"   # Chess Symbols
    "\U0001FA70-\U0001FAFF"   # Symbols & Pictographs Extended-A
    "\U00002600-\U000026FF"   # Misc Symbols
    "\U00002700-\U000027BF"   # Dingbats
    "\U0001F1E0-\U0001F1FF"   # Flags (regional indicator symbols)
    "\U00002300-\U000023FF"   # Misc Technical (includes ⌚ ⏰ ⌨ etc.)
    "\U0001F000-\U0001F02F"   # Mahjong
    "\U0001F0A0-\U0001F0FF"   # Playing Cards
    "\u2B00-\u2BFF"           # Misc Symbols & Arrows
    "\u200d"                  # ZWJ
    "\ufe0f"                  # Variation Selector-16
    "\u20e3"                  # Combining keycap
    "\u3030"                  # Wavy dash
    "]+",
    flags=re.UNICODE,
)

# Invisible / directional control characters. These are the nuclear option
# against 逆天昵称 with zero-width joiners, RTL overrides, etc.
_INVISIBLE_RE = re.compile(
    "["
    "\u200b-\u200f"     # zero-width + directional marks
    "\u202a-\u202e"     # bidi embedding / override
    "\u2066-\u2069"     # isolate
    "\ufeff"            # BOM
    "\u00ad"            # soft hyphen
    "\u180e"            # Mongolian vowel separator
    "\u2028\u2029"      # line/paragraph separators
    "]"
)

# Command prefixes we should strip from the plain-text part.
# `@` is not included because that's a MessageComponent, not text.
_COMMAND_STRIP_PREFIXES = ("/群友说", "群友说", "/say", "/quote")


# ── Event parsing ─────────────────────────────────────────────────────────


def parse_at_and_text(event: AstrMessageEvent) -> Tuple[Optional[str], str]:
    """Extract (first_at_qq, raw_text) from the incoming message.

    - Only the first ``At`` component is returned.
    - All ``Plain`` fragments are concatenated in order.
    - The command prefix (e.g. ``/群友说``) is stripped from the leading
      whitespace of the text so the caller just sees the argument.
    """
    target_qq: Optional[str] = None
    text_parts: list[str] = []

    for seg in event.message_obj.message:
        if isinstance(seg, At) and target_qq is None:
            target_qq = str(seg.qq)
            continue
        if isinstance(seg, Plain):
            text_parts.append(seg.text)

    raw = "".join(text_parts)

    stripped = raw.lstrip()
    for prefix in _COMMAND_STRIP_PREFIXES:
        if stripped.startswith(prefix):
            raw = stripped[len(prefix):]
            break

    return target_qq, raw.strip()


# ── String sanitization ───────────────────────────────────────────────────


def sanitize_nickname(
    s: str,
    max_len: int = 20,
    strip_emoji: bool = True,
) -> str:
    """Clean a QQ group nickname so it renders predictably with Pillow.

    Strategy (in order):
    1. NFKC normalize (wide-to-narrow, ligatures → base characters).
    2. Strip invisible / bidi / control characters.
    3. Drop any Unicode General Category starting with ``C`` (Cc, Cf, Co, Cs, Cn).
    4. Optionally strip emoji.
    5. Collapse whitespace.
    6. Truncate to ``max_len`` (appending ``…``).
    """
    if not s:
        return "(匿名)"

    s = unicodedata.normalize("NFKC", s)
    s = _INVISIBLE_RE.sub("", s)
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")

    if strip_emoji:
        s = _EMOJI_RE.sub("", s)

    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return "(匿名)"

    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def sanitize_body(s: str, max_len: int = 200) -> str:
    """Lighter touch — keep the user's text mostly intact, only kill
    invisibles and hard truncate. Preserves intentional newlines.
    """
    if not s:
        return ""
    s = _INVISIBLE_RE.sub("", s)
    s = "".join(
        ch for ch in s
        if ch == "\n" or unicodedata.category(ch)[0] != "C"
    )
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s
