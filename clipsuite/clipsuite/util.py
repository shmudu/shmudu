"""Small shared helpers: running tools, probing media, reading/writing job files."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

WORKSPACE = Path(os.environ.get("CLIPSUITE_WORKSPACE", Path.cwd() / "workspace"))


class ToolMissing(RuntimeError):
    """Raised when an external program (ffmpeg, yt-dlp, npx...) is not installed."""


def require(tool: str, hint: str = "") -> str:
    path = shutil.which(tool)
    if not path:
        msg = f"'{tool}' is not installed or not on PATH."
        if hint:
            msg += f" {hint}"
        raise ToolMissing(msg)
    return path


FFMPEG_LIBASS_FIX = (
    "Your FFmpeg was built without libass, which burned-in captions need. On a Mac:\n"
    "  brew uninstall --ignore-dependencies ffmpeg\n"
    "  brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg"
)


def ffmpeg_has_filter(name: str) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def run(cmd: Iterable[str], cwd: Path | None = None, quiet: bool = False) -> subprocess.CompletedProcess:
    cmd = [str(c) for c in cmd]
    if not quiet:
        print("$", " ".join(_shell_quote(c) for c in cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-25:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd[0]}\n" + "\n".join(tail))
    return proc


def _shell_quote(s: str) -> str:
    return s if re.fullmatch(r"[\w@%+=:,./-]+", s) else "'" + s.replace("'", "'\\''") + "'"


def probe(path: Path) -> dict[str, Any]:
    """Return duration, width, height, fps, has_audio for a media file."""
    require("ffprobe", "Install FFmpeg (brew install ffmpeg).")
    out = run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        quiet=True,
    ).stdout
    data = json.loads(out)
    info: dict[str, Any] = {"duration": float(data["format"].get("duration", 0.0)), "has_audio": False}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and "width" not in info:
            info["width"], info["height"] = int(s["width"]), int(s["height"])
            num, _, den = s.get("avg_frame_rate", "30/1").partition("/")
            try:
                info["fps"] = round(float(num) / float(den or 1), 3) or 30.0
            except (ValueError, ZeroDivisionError):
                info["fps"] = 30.0
        elif s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (slug[:max_len].rstrip("-")) or "clip"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)
    return path


def job_dir(job_id: str) -> Path:
    return WORKSPACE / job_id


def list_jobs() -> list[dict[str, Any]]:
    if not WORKSPACE.exists():
        return []
    jobs = []
    for d in sorted(WORKSPACE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = read_json(d / "job.json")
        if meta:
            jobs.append(meta)
    return jobs


def fmt_ts(seconds: float, sep: str = ",") -> str:
    """00:01:02,345 style timestamp (SRT uses ',' and VTT uses '.')."""
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"
