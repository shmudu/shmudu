"""DaVinci Resolve hand-off.

`export_fcpxml` writes an FCPXML 1.9 file Resolve imports with
File > Import > Timeline (works in the free version):
  * "Selects" timeline: every clip cut from the original 16:9 source, so you can
    re-trim in context, then reframe with Resolve's Smart Reframe.
  * one 1080x1920 timeline per clip using raw.mp4 (no burned captions), plus the
    clip's .srt you can drop onto a subtitle track.

`push_to_resolve` drives a running Resolve through its scripting API to do the
import for you (Preferences > System > General > External scripting using: Local).
"""

from __future__ import annotations

import os
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from .util import probe, read_json

MAC_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
MAC_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"


def _frame_duration(fps: float) -> Fraction:
    common = {23.976: Fraction(1001, 24000), 29.97: Fraction(1001, 30000), 59.94: Fraction(1001, 60000)}
    for k, v in common.items():
        if abs(fps - k) < 0.01:
            return v
    return Fraction(1, int(round(fps or 30)))


def _t(seconds: float, fd: Fraction) -> str:
    """Seconds -> FCPXML rational time snapped to whole frames."""
    frames = round(Fraction(seconds).limit_denominator(100000) / fd)
    val = frames * fd
    return f"{val.numerator}/{val.denominator}s" if val.denominator != 1 else f"{val.numerator}s"


def export_fcpxml(job: Path) -> Path:
    clips = read_json(job / "clips.json") or []
    meta = read_json(job / "job.json", {})
    src = (job / "source.mp4").resolve()
    sinfo = meta.get("media") or probe(src)
    sfd = _frame_duration(sinfo.get("fps", 30))
    vfd = Fraction(1, 30)

    res = [
        f'<format id="fsrc" name="Source" frameDuration="{_t(float(sfd), sfd)}" '
        f'width="{sinfo["width"]}" height="{sinfo["height"]}"/>',
        f'<format id="fvert" name="Vertical1080x1920p30" frameDuration="1/30s" width="1080" height="1920"/>',
        f'<asset id="asrc" name={quoteattr(meta.get("title", "source"))} start="0s" '
        f'duration="{_t(sinfo["duration"], sfd)}" hasVideo="1" hasAudio="1" format="fsrc" audioSources="1" '
        f'audioChannels="2"><media-rep kind="original-media" src={quoteattr(src.as_uri())}/></asset>',
    ]
    projects = []

    # Selects timeline (source aspect)
    offset, spine = 0.0, []
    for c in clips:
        d = c["end"] - c["start"]
        spine.append(f'<asset-clip ref="asrc" name={quoteattr(c.get("title", c["id"]))} offset="{_t(offset, sfd)}" '
                     f'start="{_t(c["start"], sfd)}" duration="{_t(d, sfd)}" format="fsrc" tcFormat="NDF"/>')
        offset += d
    projects.append(_project(f"{meta.get('title', job.name)} - Selects", "fsrc", _t(offset, sfd), spine))

    # One vertical timeline per rendered clip
    for i, c in enumerate(clips):
        raw = job / "clips" / c["id"] / "raw.mp4"
        if not raw.exists():
            continue
        d = probe(raw)["duration"]
        aid = f"av{i}"
        res.append(f'<asset id="{aid}" name={quoteattr(c["id"])} start="0s" duration="{_t(d, vfd)}" hasVideo="1" '
                   f'hasAudio="1" format="fvert" audioSources="1" audioChannels="2">'
                   f'<media-rep kind="original-media" src={quoteattr(raw.resolve().as_uri())}/></asset>')
        clip_el = (f'<asset-clip ref="{aid}" name={quoteattr(c.get("title", c["id"]))} offset="0s" start="0s" '
                   f'duration="{_t(d, vfd)}" format="fvert" tcFormat="NDF"/>')
        projects.append(_project(f"Short {c['id']}", "fvert", _t(d, vfd), [clip_el]))

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n'
           "  <resources>\n    " + "\n    ".join(res) + "\n  </resources>\n"
           '  <library>\n    <event name="ClipSuite">\n' + "\n".join(projects) +
           "\n    </event>\n  </library>\n</fcpxml>\n")
    out = job / "exports" / "resolve.fcpxml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml)
    return out


def _project(name: str, fmt: str, dur: str, spine: list[str]) -> str:
    body = "\n".join("            " + s for s in spine)
    return (f"      <project name={quoteattr(name)}>\n"
            f'        <sequence format="{fmt}" duration="{dur}" tcStart="0s" tcFormat="NDF" '
            f'audioLayout="stereo" audioRate="48k">\n          <spine>\n{body}\n          </spine>\n'
            f"        </sequence>\n      </project>")


def _connect():
    api = os.environ.get("RESOLVE_SCRIPT_API", MAC_API)
    os.environ.setdefault("RESOLVE_SCRIPT_API", api)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", MAC_LIB)
    sys.path.append(os.path.join(api, "Modules"))
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as e:
        raise RuntimeError("Resolve scripting module not found. Is DaVinci Resolve installed?") from e
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError(
            "Could not reach Resolve. Open Resolve, then set Preferences > System > General > "
            "'External scripting using' to Local. (If your version doesn't allow it, use "
            "File > Import > Timeline with exports/resolve.fcpxml instead.)"
        )
    return resolve


def push_to_resolve(job: Path, project_name: str | None = None) -> str:
    fcpxml = export_fcpxml(job)
    resolve = _connect()
    pm = resolve.GetProjectManager()
    name = project_name or f"ClipSuite {job.name}"
    project = pm.LoadProject(name) or pm.CreateProject(name)
    project.SetSetting("timelineFrameRate", "30")
    mp = project.GetMediaPool()
    srts = [str(p) for p in sorted((job / "clips").glob("*/captions.srt"))]
    if srts:
        mp.ImportMedia(srts)
    tl = mp.ImportTimelineFromFile(str(fcpxml), {"timelineName": name, "importSourceClips": True})
    if not tl:
        raise RuntimeError(f"Resolve refused the import. Try File > Import > Timeline with {fcpxml}")
    resolve.OpenPage("edit")
    return name
