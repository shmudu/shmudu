"""Speaker tracking for vertical crops (podcasts, interviews, streams).

1. Sample the clip a few times a second and find faces (OpenCV).
2. Group face positions into "seats" (people who stay in roughly the same place).
3. Each moment, the active speaker is the seat whose mouth area moves most.
4. Smooth that into shots (no flicker: a speaker holds the frame for at least ~1.5 s)
   and render with hard cuts between speakers, like an edited podcast.

Modes used by render.py:
  speaker  one 9:16 crop that cuts to whoever is talking (falls back to a static face crop)
  split    two people stacked top/bottom, each cropped to their own face
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from statistics import median
from typing import Any

SAMPLE_FPS = 4.0
MIN_SHOT = 1.5     # seconds a speaker keeps the frame before we cut away
VOTE_WINDOW = 0.75  # seconds either side used to decide who's talking


def available() -> bool:
    if not importlib.util.find_spec("cv2"):
        return False
    try:
        import cv2  # type: ignore
        return not cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").empty()
    except Exception:
        return False


# --------------------------------------------------------------------------- analysis

def sample_faces(video: Path, start: float, end: float, fps: float = SAMPLE_FPS) -> list[dict[str, Any]]:
    """[{t, faces: [{x, w, motion}]}], x/w as fractions of frame width, t relative to `start`."""
    import cv2  # type: ignore
    import numpy as np

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    samples, prev_gray, idx = [], None, 0
    while True:
        t = start + idx / src_fps
        if t > end:
            break
        if idx % step:
            if not cap.grab():
                break
            idx += 1
            continue
        ok, frame = cap.read()
        idx += 1
        if not ok:
            break
        h, w = frame.shape[:2]
        scale = 640 / w
        small = cv2.resize(frame, (640, int(h * scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = []
        for (fx, fy, fw, fh) in cascade.detectMultiScale(gray, 1.1, 5, minSize=(28, 28)):
            motion = 0.0
            if prev_gray is not None:  # mouth = lower-middle of the face box
                y0, y1 = fy + int(fh * 0.62), min(gray.shape[0], fy + int(fh * 0.98))
                x0, x1 = fx + int(fw * 0.22), fx + int(fw * 0.78)
                a = gray[y0:y1, x0:x1].astype(np.int16)
                b = prev_gray[y0:y1, x0:x1].astype(np.int16)
                if a.size:
                    motion = float(np.abs(a - b).mean())
            faces.append({"x": (fx + fw / 2) / 640, "w": fw / 640, "motion": motion})
        samples.append({"t": round(t - start, 3), "faces": faces})
        prev_gray = gray
    cap.release()
    return samples


def find_seats(samples: list[dict[str, Any]], gap: float = 0.12, min_share: float = 0.15) -> list[float]:
    """Cluster face x-positions into seats; keep seats seen in at least `min_share` of samples."""
    xs = sorted(f["x"] for s in samples for f in s["faces"])
    if not xs:
        return []
    groups, cur = [], [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > gap:
            groups.append(cur)
            cur = []
        cur.append(x)
    groups.append(cur)
    n = max(1, len(samples))
    seats = [median(g) for g in groups if len(g) / n >= min_share]
    return seats[:3]


def _seat_of(x: float, seats: list[float]) -> int:
    return min(range(len(seats)), key=lambda i: abs(seats[i] - x))


def speaker_shots(samples: list[dict[str, Any]], seats: list[float], duration: float) -> list[dict[str, Any]]:
    """[{start, end, seat}] covering the clip, cutting to the active speaker."""
    if not seats:
        return []
    if len(seats) == 1:
        return [{"start": 0.0, "end": duration, "seat": 0}]
    # 1. per-sample loudest mouth
    raw = []
    for s in samples:
        best, best_m = None, 0.0
        for f in s["faces"]:
            if f["motion"] > best_m:
                best, best_m = _seat_of(f["x"], seats), f["motion"]
        raw.append(best)
    # 2. majority vote in a sliding window (ignores blinks / head turns)
    k = max(1, round(VOTE_WINDOW * SAMPLE_FPS))
    voted, last = [], 0
    for i in range(len(raw)):
        window = [r for r in raw[max(0, i - k): i + k + 1] if r is not None]
        if window:
            last = max(set(window), key=window.count)
        voted.append(last)
    # 3. turn into shots and absorb ones shorter than MIN_SHOT into the previous shot
    times = [s["t"] for s in samples] or [0.0]
    shots: list[dict[str, Any]] = []
    for i, seat in enumerate(voted):
        t = times[i]
        if shots and shots[-1]["seat"] == seat:
            continue
        if shots:
            shots[-1]["end"] = t
        shots.append({"start": t, "end": duration, "seat": seat})
    if not shots:
        return [{"start": 0.0, "end": duration, "seat": 0}]
    shots[0]["start"] = 0.0
    merged: list[dict[str, Any]] = []
    for sh in shots:
        if merged and (sh["end"] - sh["start"] < MIN_SHOT or merged[-1]["seat"] == sh["seat"]):
            merged[-1]["end"] = sh["end"]
        else:
            merged.append(dict(sh))
    if len(merged) > 1 and merged[0]["end"] - merged[0]["start"] < MIN_SHOT:  # short opening shot
        merged[1]["start"] = 0.0
        merged.pop(0)
    merged[-1]["end"] = duration
    return [{"start": round(m["start"], 3), "end": round(m["end"], 3), "seat": m["seat"]} for m in merged]


def plan(video: Path, start: float, end: float) -> dict[str, Any] | None:
    """Analyse a clip: seats (x positions) and speaker shots. None if no faces were found."""
    if not available():
        return None
    samples = sample_faces(video, start, end)
    seats = find_seats(samples)
    if not seats:
        return None
    return {"seats": [round(x, 4) for x in seats], "shots": speaker_shots(samples, seats, end - start)}


# --------------------------------------------------------------------------- ffmpeg filters

def _crop_x(center: float, src_w: int, crop_w: int) -> int:
    return int(max(0, min(src_w - crop_w, center * src_w - crop_w / 2)))


def speaker_filter(track: dict[str, Any], src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    """One 9:16 crop whose x jumps to the current speaker's seat (per-frame crop expression)."""
    crop_w = min(src_w, round(src_h * out_w / out_h / 2) * 2)
    xs = [_crop_x(track["seats"][sh["seat"]], src_w, crop_w) for sh in track["shots"]]
    expr = str(xs[-1])
    for sh, x in zip(reversed(track["shots"][:-1]), reversed(xs[:-1])):
        expr = f"if(lt(t\\,{sh['end']:.3f})\\,{x}\\,{expr})"
    return f"crop={crop_w}:{src_h}:{expr}:0,scale={out_w}:{out_h}"


def split_filter(track: dict[str, Any], src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    """Two seats stacked: left seat on top, right seat below, each framed on its face."""
    seats = sorted(track["seats"])[:2]
    if len(seats) < 2:
        return speaker_filter(track, src_w, src_h, out_w, out_h)
    half = out_h // 2
    crop_w = min(src_w, round(src_h * out_w / half / 2) * 2)
    crop_h = src_h if crop_w < src_w else round(src_w * half / out_w / 2) * 2
    top, bottom = (_crop_x(x, src_w, crop_w) for x in seats)
    return (f"split[sa][sb];[sa]crop={crop_w}:{crop_h}:{top}:0,scale={out_w}:{half}[top];"
            f"[sb]crop={crop_w}:{crop_h}:{bottom}:0,scale={out_w}:{half}[bot];[top][bot]vstack")
