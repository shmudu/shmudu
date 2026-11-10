"""Character sprites and background art for `clipsuite create --style cartoon`.

  clipsuite character add dave-before art.png --part left   # cut the left figure out of a 2-up image
  clipsuite character add dave-after  art.png --part right
  clipsuite character list
  clipsuite background add bedroom my-bedroom.png           # replace a built-in background

Sprites are stored as transparent PNGs in workspace/_characters, backgrounds in
workspace/_backgrounds. Art on a plain white (or any flat) background is cut out
automatically; art that's already transparent is kept as is.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import util

IMAGE_EXTS = (".png", ".webp", ".jpg", ".jpeg")


def char_dir() -> Path:
    return util.WORKSPACE / "_characters"


def bg_dir() -> Path:
    return util.WORKSPACE / "_backgrounds"


def _pixels(img):
    """Pixel iterator across Pillow versions (getdata is deprecated in newer releases)."""
    return img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()


def _pil():
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install pillow") from e
    return Image, ImageDraw


def cut_out(src: Path, part: str = "full", tolerance: int = 38) -> "Image.Image":  # noqa: F821
    """Remove a flat background by flood-filling from the image edges, then trim."""
    Image, ImageDraw = _pil()
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    if part in ("left", "right"):
        img = img.crop((0, 0, w // 2, h) if part == "left" else (w // 2, 0, w, h))
        w, h = img.size

    alpha = img.getchannel("A")
    if alpha.getextrema()[0] < 250:  # already has transparency: keep it
        out = img
    else:
        rgb = img.convert("RGB")
        key = (255, 0, 255)
        seeds = [(x, y) for x in range(0, w, 24) for y in (0, h - 1)] + \
                [(x, y) for y in range(0, h, 24) for x in (0, w - 1)]
        bg = rgb.getpixel((0, 0))
        for sx, sy in seeds:
            px = rgb.getpixel((sx, sy))
            if px == key or sum(abs(a - b) for a, b in zip(px, bg)) > tolerance * 3:
                continue
            ImageDraw.floodfill(rgb, (sx, sy), key, thresh=tolerance)
        _clear_enclosed_white(rgb, key, ImageDraw, min_area=int(w * h * 0.0006))
        mask = Image.new("L", (w, h))
        mask.putdata([0 if p == key else 255 for p in _pixels(rgb)])
        out = img.copy()
        out.putalpha(mask)
    bbox = out.getchannel("A").getbbox()
    if bbox:
        pad = 4
        out = out.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(w, bbox[2] + pad), min(h, bbox[3] + pad)))
    return out


def _clear_enclosed_white(rgb, key, ImageDraw, min_area: int) -> None:
    """Background showing through gaps (between an arm and the body) isn't connected to the
    edge, so the edge fill misses it. Clear large pure-white islands; keep small ones (eyes, teeth)."""
    w, h = rgb.size
    probe, keep = (1, 254, 1), (254, 254, 254)
    for y in range(0, h, 6):
        for x in range(0, w, 6):
            px = rgb.getpixel((x, y))
            if px in (key, keep) or min(px) < 246:
                continue
            ImageDraw.floodfill(rgb, (x, y), probe, thresh=14)
            area = sum(1 for p in _pixels(rgb) if p == probe)
            ImageDraw.floodfill(rgb, (x, y), key if area >= min_area else keep, thresh=0)


def add_character(name: str, src: Path, part: str = "full", keep_background: bool = False) -> Path:
    Image, _ = _pil()
    char_dir().mkdir(parents=True, exist_ok=True)
    dest = char_dir() / f"{name}.png"
    if keep_background:
        img = Image.open(src).convert("RGBA")
        w, h = img.size
        if part in ("left", "right"):
            img = img.crop((0, 0, w // 2, h) if part == "left" else (w // 2, 0, w, h))
    else:
        img = cut_out(Path(src).expanduser(), part)
    img.save(dest)
    return dest


def add_background(name: str, src: Path) -> Path:
    bg_dir().mkdir(parents=True, exist_ok=True)
    src = Path(src).expanduser()
    for old in bg_dir().glob(f"{name}.*"):
        old.unlink()
    dest = bg_dir() / f"{name}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return dest


def find(directory: Path, name: str) -> Path | None:
    for ext in IMAGE_EXTS:
        p = directory / f"{name}{ext}"
        if p.exists():
            return p
    return None


def list_all() -> dict[str, list[str]]:
    return {
        "characters": sorted(p.stem for p in char_dir().glob("*.png")) if char_dir().exists() else [],
        "backgrounds": sorted(p.stem for p in bg_dir().iterdir()) if bg_dir().exists() else [],
    }
