"""CLI: turn a bubble image into a groupsays theme directory.

Three input modes, in order of "how automated":

    1. **Android .9.png** (deterministic) — the standard format. Markers
       on the 1-px transparent border tell us the 9-slice geometry and
       content padding. Produced by Android Studio's draw-9-patch tool
       or extracted from APK ``res/drawable-*/`` resources.

    2. **Plain PNG** (heuristic) — any rectangular bubble image. We
       scan pixel rows / columns to detect where the rounded corners
       end and the stretchable interior begins. Not perfect; works
       best on solid-colored or simply-bordered bubbles. The user can
       hand-edit the produced ``manifest.json`` to fix wrong guesses.

    3. **Directory dump** (e.g. unzipped APK) — recursively scans for
       ``.png`` / ``.9.png`` files; prints a list of likely bubble
       candidates (filename hints + size sanity check) so the user can
       pick one and re-run mode 1 or 2 on it. We do NOT auto-decrypt
       Tencent's proprietary skin packages.

Usage::

    python -m astrbot_plugin_groupsays.tools.import_theme INPUT NAME [--out DIR] [--dry-run]

    # 9-patch (no manual tuning needed):
    python -m astrbot_plugin_groupsays.tools.import_theme bubble.9.png classic

    # plain PNG with heuristic detection:
    python -m astrbot_plugin_groupsays.tools.import_theme my_bubble.png mytheme

    # scan a directory for candidates:
    python -m astrbot_plugin_groupsays.tools.import_theme ~/qq_apk_unzip --scan

Output: writes ``<DIR>/<NAME>/{manifest.json, body.png}``. Default
output dir is ``./themes``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from PIL import Image

# Allow running as a package (`-m astrbot_plugin_groupsays.tools.import_theme`),
# as a module under tools (`from tools.import_theme import ...`), and as a bare
# script (`python tools/import_theme.py ...`). Try each import strategy in
# turn and pick the first that works.
heuristic_9slice = None
parse_9patch_markers = None
for _strategy in (
    lambda: __import__("astrbot_plugin_groupsays.theme", fromlist=["x"]),
    lambda: __import__("..theme", fromlist=["x"], level=0),
    lambda: (
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        or __import__("theme")
    ),
):
    try:
        _t = _strategy()
        heuristic_9slice = _t.heuristic_9slice
        parse_9patch_markers = _t.parse_9patch_markers
        break
    except Exception:
        continue
if heuristic_9slice is None:
    # Last resort — ensure the plugin dir is on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from theme import heuristic_9slice, parse_9patch_markers  # type: ignore


# Heuristic file-name hints for "this might be a bubble"
BUBBLE_NAME_HINTS = [
    "bubble", "speech", "balloon", "chatbg",
    "气泡", "对话", "聊天",
]


def import_one(
    src_path: Path,
    name: str,
    out_dir: Path,
    *,
    dry_run: bool = False,
) -> dict:
    """Import one image into a theme. Returns the manifest dict."""
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    img = Image.open(src_path).convert("RGBA")
    is_9patch = src_path.name.endswith(".9.png")

    if is_9patch:
        slice_pad, content_pad = parse_9patch_markers(img)
        # Strip the marker border for storage
        body_img = img.crop((1, 1, img.width - 1, img.height - 1))
        method = "9-patch markers (deterministic)"
    else:
        slice_pad = heuristic_9slice(img)
        # Heuristic doesn't infer content padding; default to 9-slice pad + small inset.
        pt, pl, pb, pr = slice_pad
        content_pad = (pt + 4, pl + 6, pb + 4, pr + 6)
        body_img = img
        method = "heuristic (auto-detected, may need tweaking)"

    # Sanity check
    src_w, src_h = body_img.size
    pt, pl, pb, pr = slice_pad
    if pt + pb >= src_h or pl + pr >= src_w:
        raise ValueError(
            f"detected 9-slice padding {slice_pad} would leave no center area "
            f"(image is {src_w}×{src_h})"
        )

    target_dir = out_dir / name
    body_filename = "body.png"

    manifest = {
        "name": name,
        "body": body_filename,
        "padding_9slice": list(slice_pad),
        "padding_content": list(content_pad),
        "text_color": "#000000",
        "_meta": {
            "imported_from": str(src_path.name),
            "detection_method": method,
        },
    }

    print(f"Source         : {src_path}")
    print(f"Image size     : {src_w}×{src_h}")
    print(f"Detection      : {method}")
    print(f"padding_9slice : (top={pt}, left={pl}, bottom={pb}, right={pr})")
    print(f"padding_content: {tuple(content_pad)}")
    print(f"Output         : {target_dir}/")

    if dry_run:
        print("(dry run — no files written)")
        return manifest

    target_dir.mkdir(parents=True, exist_ok=True)
    body_img.save(target_dir / body_filename, "PNG")
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("✓ written.")
    return manifest


def scan_directory(root: Path) -> List[Path]:
    """Recursively scan ``root`` for likely bubble PNG candidates."""
    if not root.is_dir():
        raise NotADirectoryError(root)
    cands: List[tuple[Path, int]] = []   # (path, score)
    for p in root.rglob("*.png"):
        # Skip tiny icons (likely not bubbles)
        try:
            with Image.open(p) as im:
                w, h = im.size
        except Exception:
            continue
        if w < 60 or h < 40:
            continue
        # Score: filename keywords + aspect ratio (bubbles wider than tall)
        score = 0
        lower = p.name.lower()
        for hint in BUBBLE_NAME_HINTS:
            if hint in lower:
                score += 10
        if 1.0 < (w / h) < 4.0:
            score += 1
        if w * h > 200 * 80:
            score += 1
        cands.append((p, score))
    cands.sort(key=lambda x: -x[1])
    return [p for p, _ in cands[:30]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="import_theme",
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="path to PNG / 9.png file, or directory to --scan")
    p.add_argument("name", nargs="?", help="theme name (required unless --scan)")
    p.add_argument(
        "--out", default="./themes",
        help="output directory for the theme (default: ./themes)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="print detected metadata without writing files",
    )
    p.add_argument(
        "--scan", action="store_true",
        help="scan a directory for candidate bubble PNGs (no theme created)",
    )
    args = p.parse_args(argv)

    src = Path(args.input).expanduser()

    if args.scan:
        if not src.is_dir():
            print(f"--scan requires a directory, got {src}", file=sys.stderr)
            return 2
        cands = scan_directory(src)
        if not cands:
            print("(no candidate PNGs found)")
            return 0
        print(f"Top {len(cands)} candidate bubble PNGs in {src}:")
        for c in cands:
            try:
                with Image.open(c) as im:
                    w, h = im.size
            except Exception:
                w, h = -1, -1
            print(f"  {w:>4}×{h:<4}  {c}")
        print()
        print("Pick one and re-run without --scan:")
        print(f"  python -m astrbot_plugin_groupsays.tools.import_theme <path> <name>")
        return 0

    if not args.name:
        print("error: NAME required (theme directory name)", file=sys.stderr)
        return 2
    if not src.is_file():
        print(f"error: not a file: {src}", file=sys.stderr)
        return 2

    out_dir = Path(args.out).expanduser()
    try:
        import_one(src, args.name, out_dir, dry_run=args.dry_run)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
