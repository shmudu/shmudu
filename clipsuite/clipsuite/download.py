"""Fetch source videos with yt-dlp (or import a local file)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from .util import job_dir, probe, require, run, slugify, write_json


def new_job(title: str) -> Path:
    job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + slugify(title, 32)
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, max_height: int = 1080) -> Path:
    """Download a URL into a new job folder. Returns the job directory."""
    require("yt-dlp", "Install with: brew install yt-dlp")
    title = run(["yt-dlp", "--no-playlist", "--print", "title", "--skip-download", url], quiet=True).stdout.strip()
    d = new_job(title or "video")
    run([
        "yt-dlp", "--no-playlist",
        "-f", f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/b[height<={max_height}]/bv*+ba/b",
        "--merge-output-format", "mp4",
        "--write-info-json", "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-o", str(d / "source.%(ext)s"),
        url,
    ])
    src = d / "source.mp4"
    if not src.exists():  # some sites ignore the merge format
        candidates = [p for p in d.glob("source.*") if p.suffix not in {".json", ".jpg", ".webp", ".part"}]
        if not candidates:
            raise RuntimeError("yt-dlp finished but no video file was found")
        candidates[0].rename(src)
    _write_meta(d, title=title or "video", source=url)
    return d


def import_file(path: Path) -> Path:
    """Copy a local video into a new job folder."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    d = new_job(path.stem)
    dest = d / "source.mp4"
    if path.suffix.lower() == ".mp4":
        shutil.copy2(path, dest)
    else:
        require("ffmpeg")
        run(["ffmpeg", "-y", "-i", path, "-c:v", "libx264", "-crf", "18", "-c:a", "aac", dest])
    _write_meta(d, title=path.stem, source=str(path))
    return d


def _write_meta(d: Path, title: str, source: str) -> None:
    info = probe(d / "source.mp4")
    write_json(d / "job.json", {
        "id": d.name, "title": title, "source": source,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "media": info, "status": "downloaded",
    })
