"""HyperFrames (HeyGen's open-source HTML-to-video renderer) for motion-graphic
intro hook cards and outro call-to-action cards, stitched around a clip.

Each card is a tiny HyperFrames project (an index.html with GSAP animation) in
workspace/<job>/clips/<id>/hyperframes/<intro|outro>/. Edit the HTML by hand or
with an AI agent, preview with `npx hyperframes preview`, and re-run this step.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .util import read_json, require, run

TEMPLATE = (Path(__file__).resolve().parent.parent / "hyperframes" / "templates" / "card.html").read_text


def write_card(folder: Path, comp_id: str, headline: str, sub: str, seconds: float, accent: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    page = (TEMPLATE()
            .replace("{{COMP_ID}}", comp_id)
            .replace("{{HEADLINE}}", html.escape(headline))
            .replace("{{SUB}}", html.escape(sub))
            .replace("{{SECONDS}}", f"{seconds:g}")
            .replace("{{ACCENT}}", accent))
    (folder / "index.html").write_text(page)
    return folder


def render_card(folder: Path) -> Path:
    require("npx", "Install Node.js 22+ (brew install node).")
    out = folder / "card.mp4"
    run(["npx", "--yes", "hyperframes", "render", "-o", "card.mp4"], cwd=folder)
    return out


def build(job: Path, clip_id: str, cta: str = "Follow for part 2", intro_secs: float = 1.6,
          outro_secs: float = 2.0, accent: str = "#FFE500", render: bool = True) -> Path:
    clip: dict[str, Any] = {c["id"]: c for c in read_json(job / "clips.json", [])}[clip_id]
    base = job / "clips" / clip_id
    hf = base / "hyperframes"
    intro = write_card(hf / "intro", "intro", clip.get("title", ""), "", intro_secs, accent)
    outro = write_card(hf / "outro", "outro", cta, read_json(job / "job.json", {}).get("title", ""), outro_secs, accent)
    if not render:
        return hf
    parts = [render_card(intro), base / "final.mp4", render_card(outro)]
    return stitch(parts, base / "final-with-cards.mp4")


def stitch(parts: list[Path], out: Path) -> Path:
    """Concatenate videos (re-encoding so sizes/codecs match); cards get silent audio."""
    require("ffmpeg")
    inputs, filters = [], []
    for i, p in enumerate(parts):
        inputs += ["-i", p]
        filters.append(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
                       f"fps=30,format=yuv420p,setsar=1[v{i}]")
    n = len(parts)
    # anullsrc gives each card a silent track so concat has matching audio streams
    for i, p in enumerate(parts):
        if _has_audio(p):
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{_dur(p)}[a{i}]")
    filters.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    return out


def _has_audio(p: Path) -> bool:
    from .util import probe
    return probe(p)["has_audio"]


def _dur(p: Path) -> float:
    from .util import probe
    return probe(p)["duration"]
