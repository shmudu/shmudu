"""Character sprites and background art for `clipsuite create --style cartoon`.

  clipsuite character add dave-before art.png --part left   # cut the left figure out of a 2-up image
  clipsuite character add dave-after  art.png --part right
  clipsuite character list
  clipsuite background add bedroom my-bedroom.png           # replace a built-in background
  clipsuite split collage.png                               # cut a multi-panel image into panels

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
        import numpy as np

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
        outside = np.all(np.asarray(rgb) == key, axis=2)
        near_edge = _dilate(outside, max(6, round(min(w, h) * 0.015)))
        _clear_enclosed_white(rgb, key, ImageDraw, int(w * h * 0.0006), near_edge)
        clear = np.all(np.asarray(rgb) == key, axis=2)
        out = _defringe(np.asarray(img.convert("RGB")), clear)
    bbox = out.getchannel("A").getbbox()
    if bbox:
        pad = 4
        out = out.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(w, bbox[2] + pad), min(h, bbox[3] + pad)))
    return out


def _dilate(mask, radius: int):
    """Grow a boolean mask by `radius` pixels (square neighbourhood), numpy only."""
    import numpy as np

    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _clear_enclosed_white(rgb, key, ImageDraw, min_area: int, near_edge) -> None:
    """Background that shows through gaps (between an arm and the body, between hair strands)
    isn't connected to the image border, so the border fill misses it. Clear white islands that
    are large, or that sit right at the silhouette's edge; keep small inner ones (eyes, teeth)."""
    import numpy as np

    w, h = rgb.size
    probe, keep = (1, 254, 1), (254, 254, 254)
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            px = rgb.getpixel((x, y))
            if px in (key, keep) or min(px) < 240:
                continue
            ImageDraw.floodfill(rgb, (x, y), probe, thresh=16)
            island = np.all(np.asarray(rgb) == probe, axis=2)
            background = island.sum() >= min_area or bool((island & near_edge).any())
            ImageDraw.floodfill(rgb, (x, y), key if background else keep, thresh=0)


def _defringe(arr, clear):
    """Alpha from the cleared mask, then 'colour to alpha' against white on the few pixels
    bordering it, so anti-aliased edges lose their white halo instead of keeping a light outline."""
    import numpy as np
    from PIL import Image

    rgb = arr.astype(np.float32)
    alpha = np.where(clear, 0.0, 1.0).astype(np.float32)
    band = _dilate(clear, 3) & ~clear
    a = np.clip((255.0 - rgb).max(axis=2) / 255.0, 0.0, 1.0)  # how far from white
    a = np.minimum(1.0, a * 1.6)  # keep mid-tones solid; only near-white edge pixels fade
    soft = band & (a < 1.0)
    alpha[soft] = a[soft]
    safe = np.maximum(alpha, 1e-3)[..., None]
    fixed = np.clip((rgb - 255.0 * (1.0 - alpha[..., None])) / safe, 0, 255)
    rgb = np.where(soft[..., None], fixed, rgb)
    rgba = np.dstack([rgb, alpha * 255.0]).round().astype(np.uint8)
    rgba[clear] = 0
    return Image.fromarray(rgba, "RGBA")


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


def split_panels(src: Path, out_dir: Path | None = None, min_gap: int = 3) -> list[tuple[Path, tuple[int, int, int, int]]]:
    """Cut a collage into its panels along full-width/height white (or black) gutters."""
    import numpy as np
    Image, _ = _pil()

    img = Image.open(src).convert("RGB")
    arr = np.asarray(img).astype(int)
    gutter = (arr.min(axis=2) > 225) | (arr.max(axis=2) < 25)

    def runs(flags):
        """(start, end) spans of non-gutter lines, splitting on gutters at least min_gap thick."""
        spans, start, gap = [], None, 0
        for i, g in enumerate(list(flags) + [True] * min_gap):
            if g:
                gap += 1
                if start is not None and gap >= min_gap:
                    spans.append((start, i - gap + 1))
                    start = None
            else:
                if start is None:
                    start = i
                gap = 0
        return [(a, b) for a, b in spans if b - a > 40]

    def split(x0, y0, x1, y1, depth=0):
        region = gutter[y0:y1, x0:x1]
        cols = runs(region.mean(axis=0) > 0.97)
        rows = runs(region.mean(axis=1) > 0.97)
        if depth < 4 and len(cols) > 1:
            return [b for a, c in cols for b in split(x0 + a, y0, x0 + c, y1, depth + 1)]
        if depth < 4 and len(rows) > 1:
            return [b for a, c in rows for b in split(x0, y0 + a, x1, y0 + c, depth + 1)]
        if cols and rows:  # trim outer gutters
            return [(x0 + cols[0][0], y0 + rows[0][0], x0 + cols[-1][1], y0 + rows[-1][1])]
        return [(x0, y0, x1, y1)]

    boxes = split(0, 0, img.width, img.height)
    out_dir = out_dir or util.WORKSPACE / "_panels"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem
    results = []
    for i, box in enumerate(boxes, 1):
        dest = out_dir / f"{stem}-{i}.png"
        img.crop(box).save(dest)
        results.append((dest, box))
    return results


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
