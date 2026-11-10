"""Cut, reframe to vertical, loudness-normalize and burn captions with FFmpeg.

For every clip two files are produced in workspace/<job>/clips/<clip-id>/:
  raw.mp4    9:16 reframed, normalized audio, NO captions (for Resolve, ChatCut, Remotion)
  final.mp4  raw + b-roll inserts + burned-in animated captions + title (ready to post)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from . import captions
from .transcribe import all_words
from .util import probe, read_json, require, run, write_json

OUT_W, OUT_H, OUT_FPS = 1080, 1920, 30


def reframe_filter(mode: str, src_w: int, src_h: int, crop_x: float = 0.5) -> str:
    """FFmpeg filter that turns any input into OUT_W x OUT_H."""
    if mode == "blur":
        return (f"split[a][b];[a]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
                f"crop={OUT_W}:{OUT_H},boxblur=30:5,eq=brightness=-0.08[bg];"
                f"[b]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    if mode == "fit":
        return (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
                f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black")
    # crop (center or at a chosen horizontal position)
    target_w = min(src_w, round(src_h * OUT_W / OUT_H / 2) * 2)
    max_x = src_w - target_w
    x = int(max(0, min(max_x, crop_x * src_w - target_w / 2)))
    return f"crop={target_w}:{src_h}:{x}:0,scale={OUT_W}:{OUT_H}"


def detect_face_x(video: Path, start: float, end: float, samples: int = 12) -> float | None:
    """Median horizontal face position (0..1) across the clip, using OpenCV if installed."""
    if not importlib.util.find_spec("cv2"):
        return None
    try:
        return _detect_face_x(video, start, end, samples)
    except Exception as e:  # a broken OpenCV install must never stop a render
        print(f"  ! face tracking unavailable ({e.__class__.__name__}: {e}); using a standard crop. "
              "Fix: run `clipsuite doctor`.", flush=True)
        return None


def _detect_face_x(video: Path, start: float, end: float, samples: int) -> float | None:
    import cv2  # type: ignore

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None
    cap = cv2.VideoCapture(str(video))
    xs = []
    for k in range(samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * (k + 0.5) / samples) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / frame.shape[1])
    cap.release()
    if not xs:
        return None
    xs.sort()
    return xs[len(xs) // 2]


def render_clip(job: Path, clip: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    require("ffmpeg", "Install FFmpeg (brew install ffmpeg).")
    defaults = defaults or {}
    style = {**defaults, **clip.get("style", {})}
    src = job / "source.mp4"
    info = read_json(job / "job.json", {}).get("media") or probe(src)
    out = job / "clips" / clip["id"]
    out.mkdir(parents=True, exist_ok=True)
    start, end = float(clip["start"]), float(clip["end"])
    dur = end - start

    mode = style.get("reframe", "auto")
    crop_x = float(style.get("crop_x", 0.5))
    if mode in ("auto", "face"):
        fx = detect_face_x(src, start, end)
        if fx is not None:
            mode, crop_x = "crop", fx
        else:
            mode = "crop" if mode == "face" else ("blur" if info["width"] / info["height"] > 1.9 else "crop")
    clip.setdefault("render", {}).update({"reframe": mode, "crop_x": round(crop_x, 3)})

    # 1) raw vertical cut
    raw = out / "raw.mp4"
    vf = reframe_filter(mode, info["width"], info["height"], crop_x) + f",fps={OUT_FPS},format=yuv420p"
    af = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
           "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
    if info.get("has_audio", True):
        cmd += ["-map", "0:a:0?", "-af", af, "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", raw]
    run(cmd)

    # 2) captions
    transcript = read_json(job / "transcript.json")
    words = captions.clip_words(all_words(transcript), start, end) if transcript else []
    write_json(out / "words.json", words)
    title = clip.get("title", "") if style.get("show_title", True) else ""
    ass, _srt = captions.write(words, out, style, OUT_W, OUT_H, title=title)

    # 3) final: b-roll overlays + burned captions
    final = out / "final.mp4"
    inputs: list[Any] = ["-i", "raw.mp4"]
    chain, last = [], "0:v"
    for n, b in enumerate(clip.get("broll", []), 1):
        f = Path(b["file"]).expanduser().resolve()
        if not f.exists():
            print(f"  ! b-roll file missing, skipped: {f}")
            continue
        at, bdur = float(b["at"]), float(b.get("duration", 3))
        inputs += ["-i", f]
        idx = len(inputs) // 2 - 1
        chain.append(f"[{idx}:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
                     f"fps={OUT_FPS},trim=0:{bdur},setpts=PTS-STARTPTS+{at}/TB[b{n}]")
        chain.append(f"[{last}][b{n}]overlay=enable='between(t,{at},{at + bdur})':eof_action=pass[o{n}]")
        last = f"o{n}"
    if style.get("captions", True) and words:
        chain.append(f"[{last}]ass={ass.name}[vout]")
    else:
        chain.append(f"[{last}]null[vout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "copy", "-movflags", "+faststart",
           final.name]
    run(cmd, cwd=out)

    # thumbnail for the web UI
    run(["ffmpeg", "-y", "-ss", f"{min(1.0, dur / 2):.2f}", "-i", final.name, "-frames:v", "1",
         "-vf", "scale=360:-2", "thumb.jpg"], cwd=out, quiet=True)
    clip["render"].update({"raw": str(raw), "final": str(final), "duration": round(dur, 3)})
    write_json(out / "clip.json", clip)
    return clip


def render_all(job: Path, only: list[str] | None = None, defaults: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    clips = read_json(job / "clips.json")
    if not clips:
        raise RuntimeError("No clips.json. Run: clipsuite pick <job>")
    for c in clips:
        if only and c["id"] not in only:
            continue
        print(f"Rendering {c['id']} ({c['end'] - c['start']:.1f}s)...", flush=True)
        render_clip(job, c, defaults)
    write_json(job / "clips.json", clips)
    return clips
