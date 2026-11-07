"""AI b-roll with Wan2GP (Wan 2.x video models for low-VRAM GPUs).

Wan2GP is a Gradio app (python wgp.py) that wants an NVIDIA (or AMD) GPU; Apple
Silicon support is experimental. So this module does not drive it directly:
  1. `prompts`  writes a prompt list per clip you paste into Wan2GP (on a GPU PC,
                a cloud GPU, or Pinokio on your Mac) - one prompt per line.
  2. `attach`   takes the videos Wan2GP produced and schedules them as
                full-screen inserts; the next `render` composites them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .util import read_json, write_json

STYLE_SUFFIX = ", vertical 9:16 composition, cinematic lighting, shallow depth of field, smooth camera motion"


def _fallback_prompts(clip: dict[str, Any], n: int = 2) -> list[str]:
    """No Claude-written prompts? Build simple ones from the clip's nouns-ish words."""
    text = clip.get("hook", "") + " " + clip.get("title", "")
    words = [w for w in re.findall(r"[A-Za-z]{5,}", text)][:6]
    subject = " ".join(words) or "an abstract concept"
    return [f"A visual metaphor for {subject}", f"Close-up b-roll illustrating {subject}"][:n]


def write_prompts(job: Path) -> Path:
    clips = read_json(job / "clips.json", [])
    out_dir = job / "exports" / "wan2gp"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines_all = []
    for c in clips:
        prompts = c.get("broll_prompts") or _fallback_prompts(c)
        full = [p.rstrip(". ") + STYLE_SUFFIX for p in prompts]
        (out_dir / f"{c['id']}.txt").write_text("\n".join(full) + "\n")
        lines_all += [f"# {c['id']}"] + full + [""]
    readme = out_dir / "prompts.txt"
    readme.write_text(
        "Paste a clip's lines into Wan2GP's prompt box (enable 'each line is a separate prompt').\n"
        "Suggested settings: Wan2.x text-to-video, 480x832 (portrait), 81 frames (~5s at 16fps).\n"
        "Then: clipsuite broll attach <job> <clip-id> <generated.mp4> --at <seconds>\n\n"
        + "\n".join(lines_all)
    )
    return readme


def attach(job: Path, clip_id: str, files: list[Path], at: list[float] | None = None,
           duration: float = 2.5) -> dict[str, Any]:
    clips = read_json(job / "clips.json", [])
    clip = next(c for c in clips if c["id"] == clip_id)
    length = clip["end"] - clip["start"]
    if not at:  # spread inserts through the middle of the clip, never over the hook
        step = (length - 4) / (len(files) + 1)
        at = [round(3 + step * (i + 1), 2) for i in range(len(files))]
    clip.setdefault("broll", [])
    for f, t in zip(files, at):
        clip["broll"].append({"file": str(Path(f).expanduser().resolve()), "at": float(t), "duration": duration})
    write_json(job / "clips.json", clips)
    return clip
