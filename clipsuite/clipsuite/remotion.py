"""Render a clip through the Remotion template in ../remotion (animated captions,
progress bar, hook title) instead of FFmpeg's burned-in .ass captions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .util import read_json, require, run, write_json

REMOTION_DIR = Path(__file__).resolve().parent.parent / "remotion"


def props_for(job: Path, clip: dict[str, Any], static_name: str) -> dict[str, Any]:
    out = job / "clips" / clip["id"]
    words = read_json(out / "words.json", [])
    style = clip.get("style", {})
    return {
        "videoFile": static_name,
        "durationInSeconds": round(clip["end"] - clip["start"], 3),
        "title": clip.get("title", "") if style.get("show_title", True) else "",
        "words": words,
        "accent": style.get("accent", "#FFE500"),
        "captionPosition": style.get("position", 0.70),
        "wordsPerLine": style.get("words_per_line", 3),
        "uppercase": style.get("uppercase", True),
    }


def render(job: Path, clip_id: str, preview: bool = False) -> Path:
    require("npx", "Install Node.js 22+ (brew install node).")
    if not (REMOTION_DIR / "node_modules").exists():
        run(["npm", "install"], cwd=REMOTION_DIR)
    clips = {c["id"]: c for c in read_json(job / "clips.json", [])}
    clip = clips[clip_id]
    raw = job / "clips" / clip_id / "raw.mp4"
    if not raw.exists():
        raise RuntimeError(f"Render the clip with FFmpeg first (clipsuite render {job.name} --only {clip_id})")

    static_name = f"clips/{job.name}-{clip_id}.mp4"
    dest = REMOTION_DIR / "public" / static_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw, dest)
    props_path = write_json(job / "clips" / clip_id / "remotion-props.json", props_for(job, clip, static_name))

    if preview:
        print("Opening Remotion Studio; pick 'CaptionedShort' and paste the props from", props_path)
        run(["npx", "remotion", "studio", "src/index.ts", f"--props={props_path}"], cwd=REMOTION_DIR)
        return props_path
    out = job / "clips" / clip_id / "remotion.mp4"
    run(["npx", "remotion", "render", "src/index.ts", "CaptionedShort", str(out), f"--props={props_path}"],
        cwd=REMOTION_DIR)
    return out
