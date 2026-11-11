"""Pick-then-choose workflow for clipping (e.g. Content Rewards campaigns).

  1. `clipsuite auto URL --review` finds up to 10 moments and makes quick previews
  2. you mark each one Keep or Skip (phone editor, or `clipsuite keep latest 1 4 7`)
  3. `clipsuite finish latest` renders only the kept clips at full quality and puts them,
     numbered, in workspace/<job>/exports/ready/ with a posting sheet (titles + captions)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import chatcut, render, resolve
from .util import read_json, slugify, write_json


def _resolve_ids(clips: list[dict[str, Any]], refs: list[str]) -> list[str]:
    """Accept clip numbers (1-based, as listed) or clip ids."""
    ids = []
    for r in refs:
        if r.isdigit() and 1 <= int(r) <= len(clips):
            ids.append(clips[int(r) - 1]["id"])
        elif any(c["id"] == r for c in clips):
            ids.append(r)
        else:
            raise ValueError(f"No clip {r!r}. Use a number from `clipsuite review` or a clip id.")
    return ids


def decide(job: Path, refs: list[str], decision: str) -> list[dict[str, Any]]:
    if decision not in ("keep", "skip", "pending"):
        raise ValueError(decision)
    clips = read_json(job / "clips.json", [])
    for cid in _resolve_ids(clips, refs):
        next(c for c in clips if c["id"] == cid)["decision"] = decision
    write_json(job / "clips.json", clips)
    return clips


def summary(job: Path) -> list[str]:
    rows = []
    for n, c in enumerate(read_json(job / "clips.json", []), 1):
        mark = {"keep": "KEEP", "skip": "skip"}.get(c.get("decision", ""), "  ? ")
        done = "rendered" if (c.get("render") or {}).get("final") else ""
        rows.append(f"{n:2d}. [{mark}] {c['end'] - c['start']:5.1f}s  {c.get('title', '')[:50]:50s} {done}")
    return rows


def export_ready(job: Path) -> Path:
    """Copy kept, rendered clips into exports/ready/ and write a posting sheet."""
    clips = read_json(job / "clips.json", [])
    meta = read_json(job / "job.json", {})
    ready = job / "exports" / "ready"
    if ready.exists():
        shutil.rmtree(ready)
    ready.mkdir(parents=True)
    sheet = [f"Source: {meta.get('title', job.name)}", f"Link: {meta.get('source', '')}", ""]
    n = 0
    for c in clips:
        final = job / "clips" / c["id"] / "final.mp4"
        if c.get("decision") != "keep" or not final.exists():
            continue
        n += 1
        name = f"{n:02d}-{slugify(c.get('title', c['id']), 40)}.mp4"
        shutil.copy2(final, ready / name)
        sheet += [f"[{n:02d}] {name}  ({c['end'] - c['start']:.0f}s)",
                  f"Title / on-screen hook: {c.get('title', '')}",
                  f"Caption idea: {c.get('hook', '').strip()}",
                  "", ]
    sheet += ["Before posting: check the campaign's rules (required tags or mentions, minimum length,",
              "allowed platforms), then post from your own account and submit the post link to the campaign."]
    (ready / "POSTING.txt").write_text("\n".join(sheet) + "\n")
    return ready


def finish(job: Path, defaults: dict[str, Any] | None = None) -> Path:
    """Render the kept clips at full quality, then build the ready folder and editor exports."""
    from .pipeline import set_status

    try:
        set_status(job, "rendering")
        render.render_all(job, defaults=defaults, kept_only=True)
        set_status(job, "exporting")
        resolve.export_fcpxml(job)
        chatcut.export(job)
        ready = export_ready(job)
        set_status(job, "done", error=None)
        return ready
    except Exception as e:
        set_status(job, "error", error=str(e))
        raise
