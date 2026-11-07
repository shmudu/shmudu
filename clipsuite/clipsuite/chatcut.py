"""ChatCut hand-off.

ChatCut is a chat-driven AI video editor (web, desktop, plus ChatGPT and
Claude Code plugins). It has no file-format import we can target, so we prepare
a bundle per clip - the clean vertical cut, captions, transcript and a written
edit brief - that you upload and paste into ChatCut's chat.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .util import read_json

BRIEF = """# Edit brief: {title}

Paste this into ChatCut after uploading `raw.mp4` (and `captions.srt` if you want to keep the timing).

Make this a polished 9:16 short for TikTok / Reels / YouTube Shorts:
1. Keep the opening line as the hook: "{hook}". Put the on-screen title "{title}" up for the first 2-3 seconds.
2. Remove dead air, long pauses and filler words ("um", "uh", repeated starts).
3. Add bold animated word-by-word captions, centred in the lower third, highlighting the active word.
4. Punch in (zoom ~110%) on emphasis moments to keep motion every 3-5 seconds.
5. Add subtle background music under the voice (ducked) and a soft whoosh on cuts.
6. Keep the total under {max_len} seconds and end on the final sentence; no fade to black.
{broll}
Why this moment was chosen: {reason}
"""


def export(job: Path, max_len: int = 60) -> Path:
    clips = read_json(job / "clips.json", [])
    root = job / "exports" / "chatcut"
    root.mkdir(parents=True, exist_ok=True)
    words_dir = job / "clips"
    for c in clips:
        src = words_dir / c["id"]
        if not (src / "raw.mp4").exists():
            continue
        d = root / c["id"]
        d.mkdir(exist_ok=True)
        for name in ("raw.mp4", "captions.srt"):
            if (src / name).exists():
                shutil.copy2(src / name, d / name)
        words = read_json(src / "words.json", [])
        (d / "transcript.txt").write_text(" ".join(w["w"] for w in words) + "\n")
        broll = ""
        if c.get("broll_prompts"):
            broll = "7. Add AI b-roll cutaways (2-3s each, not over the hook):\n" + "\n".join(
                f"   - {p}" for p in c["broll_prompts"]) + "\n"
        (d / "BRIEF.md").write_text(BRIEF.format(title=c.get("title", ""), hook=c.get("hook", ""),
                                                 reason=c.get("reason", ""), max_len=max_len, broll=broll))
    zpath = job / "exports" / "chatcut.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        for f in root.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(root))
    return zpath
