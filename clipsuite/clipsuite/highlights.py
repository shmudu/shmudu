"""Pick the best moments in a transcript to turn into shorts.

Two strategies:
  heuristic  offline, free: scores windows by hook words, pace and clean endings.
  claude     uses the Claude API (needs ANTHROPIC_API_KEY or `ant auth login`)
             to read the transcript like an editor and pick + title clips.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .util import read_json, slugify, write_json

HOOK_WORDS = {
    "secret", "mistake", "never", "always", "why", "how", "truth", "crazy", "insane", "best", "worst",
    "nobody", "everyone", "stop", "money", "million", "biggest", "wrong", "actually", "honestly",
    "story", "learned", "lesson", "realized", "problem", "hack", "trick", "rule", "fear", "free",
}
FILLER = {"um", "uh", "like", "you know", "kind of", "sort of"}

CLAUDE_MODEL = os.environ.get("CLIPSUITE_CLAUDE_MODEL", "claude-opus-5-5")


# --------------------------------------------------------------------------- heuristic

def _hook_score(text: str) -> float:
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return 0.0
    first = words[:20]
    score = sum(1.0 for w in first if w in HOOK_WORDS)
    score += 1.5 if "?" in text[:160] else 0.0
    score += 1.0 if re.search(r"\d", text[:120]) else 0.0
    score += 0.5 if first[0] in {"you", "if", "the", "this", "here's", "what", "why", "how", "never", "stop"} else 0.0
    return score


def _window_score(segs: list[dict[str, Any]]) -> tuple[float, str]:
    text = " ".join(s["text"] for s in segs)
    dur = segs[-1]["end"] - segs[0]["start"]
    n_words = sum(len(s["words"]) for s in segs) or len(text.split())
    pace = n_words / max(dur, 1)
    fillers = sum(text.lower().count(f) for f in FILLER) / max(n_words, 1)
    hook = _hook_score(segs[0]["text"] + " " + (segs[1]["text"] if len(segs) > 1 else ""))
    body = sum(1 for w in re.findall(r"[a-z']+", text.lower()) if w in HOOK_WORDS) / max(n_words, 1) * 40
    ending = 1.0 if segs[-1]["text"].rstrip().endswith((".", "!", "?")) else -1.0
    pace_score = 1.5 - abs(pace - 2.8)  # ~2.8 words/sec reads as energetic but clear
    score = hook * 1.6 + body + pace_score + ending - fillers * 20
    reasons = []
    if hook >= 2:
        reasons.append("strong opening hook")
    if pace > 2.5:
        reasons.append("fast pace")
    if ending > 0:
        reasons.append("ends on a full sentence")
    return score, ", ".join(reasons) or "solid segment"


def heuristic(transcript: dict[str, Any], count: int = 5, min_len: float = 20, max_len: float = 60) -> list[dict[str, Any]]:
    segs = [s for s in transcript["segments"] if s["text"].strip()]
    cands = []
    for i in range(len(segs)):
        for j in range(i, len(segs)):
            dur = segs[j]["end"] - segs[i]["start"]
            if dur > max_len:
                break
            if dur >= min_len:
                score, why = _window_score(segs[i:j + 1])
                cands.append((score, i, j, why))
    cands.sort(reverse=True)
    picked: list[tuple[float, int, int, str]] = []
    for c in cands:
        if all(c[2] < p[1] or c[1] > p[2] for p in picked):  # no overlap
            picked.append(c)
        if len(picked) >= count:
            break
    picked.sort(key=lambda c: c[1])
    clips = []
    for score, i, j, why in picked:
        hook = segs[i]["text"].strip()
        clips.append(_clip(segs[i]["start"], segs[j]["end"], title=_title_from(hook), hook=hook,
                           score=round(score, 2), reason=why))
    return clips


def _title_from(text: str) -> str:
    words = text.split()
    title = " ".join(words[:8]).rstrip(",.;:")
    return title + ("…" if len(words) > 8 else "")


# --------------------------------------------------------------------------- claude

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                    "score": {"type": "number"},
                    "broll_prompts": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_line", "end_line", "title", "hook", "reason", "score", "broll_prompts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def claude(transcript: dict[str, Any], count: int = 5, min_len: float = 20, max_len: float = 60,
           guidance: str = "") -> list[dict[str, Any]]:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install anthropic  to use --picker claude") from e

    segs = [s for s in transcript["segments"] if s["text"].strip()]
    lines = "\n".join(f"[{i}] ({s['start']:.1f}-{s['end']:.1f}s) {s['text']}" for i, s in enumerate(segs))
    prompt = (
        f"You are a short-form video editor. Below is a transcript split into numbered lines with timestamps.\n"
        f"Choose the {count} best self-contained moments to post as TikTok/Reels/Shorts clips.\n"
        f"Each clip must be {min_len:.0f}-{max_len:.0f} seconds long (use the timestamps), start on a line that "
        f"hooks a viewer in the first two seconds without needing earlier context, and end on a satisfying beat. "
        f"Clips must not overlap. Return start_line and end_line (inclusive) as line numbers, a punchy on-screen "
        f"title (max 8 words), the hook sentence, why it works, a 0-10 virality score, and 2 short visual prompts "
        f"for AI-generated b-roll that would illustrate the clip.\n"
        + (f"Creator guidance: {guidance}\n" if guidance else "")
        + f"\n<transcript>\n{lines}\n</transcript>"
    )
    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": CLIP_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to pick clips for this transcript; try --picker heuristic")
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    clips = []
    for c in data["clips"]:
        i, j = max(0, c["start_line"]), min(len(segs) - 1, c["end_line"])
        if j < i:
            continue
        clip = _clip(segs[i]["start"], segs[j]["end"], title=c["title"], hook=c["hook"],
                     score=c["score"], reason=c["reason"])
        clip["broll_prompts"] = c.get("broll_prompts", [])
        clips.append(clip)
    return sorted(clips, key=lambda c: c["start"])


# --------------------------------------------------------------------------- shared

def _clip(start: float, end: float, **kw: Any) -> dict[str, Any]:
    return {
        "start": round(max(0.0, start - 0.15), 3),  # tiny lead-in so the first word isn't clipped
        "end": round(end + 0.25, 3),
        **kw,
        "style": {},  # per-clip overrides edited in the web UI or clips.json
        "broll_prompts": kw.get("broll_prompts", []),
    }


def pick(job: Path, picker: str = "auto", count: int = 5, min_len: float = 20, max_len: float = 60,
         guidance: str = "") -> list[dict[str, Any]]:
    transcript = read_json(job / "transcript.json")
    if not transcript:
        raise RuntimeError("No transcript yet. Run: clipsuite transcribe <job>")
    if picker == "auto":
        has_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        picker = "claude" if has_key else "heuristic"
    if picker == "claude":
        clips = claude(transcript, count, min_len, max_len, guidance)
    else:
        clips = heuristic(transcript, count, min_len, max_len)
    for n, c in enumerate(clips, 1):
        c["id"] = f"{n:02d}-{slugify(c['title'], 32)}"
        c["picker"] = picker
    write_json(job / "clips.json", clips)
    return clips
