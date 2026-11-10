"""`clipsuite create`: make a faceless vertical video from a script (free) or a topic (Claude).

  script ──► scenes (plan.json) ──► voiceover per scene (Kokoro / macOS say / espeak-ng)
                                 └► visual per scene (Pexels stock video, or an animated title card)
         ──► stitched source.mp4 ──► Whisper word timings ──► normal ClipSuite render (captions, title)

The result is an ordinary ClipSuite job, so it shows up in the phone editor and
exports to Resolve / ChatCut like any other clip. Edit workspace/<job>/plan.json
and run `clipsuite create --rebuild <job>` to change scenes, wording or visuals.

Script format (plain text, scenes separated by blank lines):

    # 3 money habits that changed my life
    Most people never save a dollar. Here's what finally worked for me.
    > stock: piggy bank coins

    Habit one: pay yourself first, the day your paycheck lands.
    > text: PAY YOURSELF FIRST

Lines starting with ">" are directions: "> stock: <search words>" picks the
stock footage, "> text" or "> text: HEADLINE" shows an animated title card.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import captions, render, transcribe
from .download import _write_meta, new_job
from .pipeline import set_status
from .util import WORKSPACE, get_setting, probe, read_json, require, run, slugify, write_json

W, H, FPS = 1080, 1920, 30
WORDS_PER_SEC = 2.6  # typical narration pace, used for word budgets and fallback timings
STOP = set("""a an the and or but if then so of to in on at by for with from as is are was were be been being it
its this that these those i you he she we they me my your our their his her them us do does did done have has had
not no yes just very really more most much many some any all can could would should will shall may might must
here there what which who whom whose when where why how about into over after before than too also only own same
one two three first second third get got make made like""".split())

TEMPLATE = """# {title}
Write your hook here: one punchy sentence that makes people stay.
> stock: {query}

Second scene. Keep each scene to one or two sentences.
> stock: describe the footage you want

Third scene, shown as a big animated headline instead of stock footage.
> text: KEY POINT

End with a payoff or a call to action, like "Follow for part two."
> text: FOLLOW FOR MORE

# Tip: about 170-230 words total makes a 65-90 second video (TikTok pays only for 1 min+).
"""


# --------------------------------------------------------------------------- script / plan

def parse_script(text: str, default_title: str = "") -> dict[str, Any]:
    title = default_title
    scenes: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines, scene = [], {"kind": "stock", "visual": "", "headline": ""}
        for raw in block.strip().splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                body = re.sub(r"^#+\s*(title:\s*)?", "", line, flags=re.I).strip()
                if not title and not line.lower().startswith("# tip"):
                    title = body
                continue
            if line.startswith(">"):
                key, _, val = line[1:].strip().partition(":")
                key, val = key.strip().lower(), val.strip()
                if key in ("stock", "visual", "video"):
                    scene["kind"], scene["visual"] = "stock", val
                elif key in ("text", "card", "title"):
                    scene["kind"], scene["headline"] = "text", val
                continue
            lines.append(line)
        if lines:
            scene["text"] = " ".join(lines)
            scenes.append(scene)
    if not scenes:
        raise ValueError("The script has no narration. Write at least one paragraph.")
    title = title or _short(scenes[0]["text"], 8)
    for s in scenes:
        s["visual"] = s["visual"] or keywords(s["text"])
        s["headline"] = s["headline"] or _short(s["text"], 6).upper()
    return {"title": title, "scenes": scenes}


def keywords(text: str, n: int = 3) -> str:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)]
    seen: list[str] = []
    for w in sorted((w for w in words if w not in STOP), key=len, reverse=True):
        if w not in seen:
            seen.append(w)
    return " ".join(seen[:n]) or "abstract background"


def _short(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]).rstrip(",.;:!?") + ("…" if len(words) > n else "")


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "scenes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "kind": {"type": "string", "enum": ["stock", "text"]},
                "visual": {"type": "string"},
                "headline": {"type": "string"},
            },
            "required": ["text", "kind", "visual", "headline"],
            "additionalProperties": False,
        }},
    },
    "required": ["title", "scenes"],
    "additionalProperties": False,
}


def plan_with_claude(topic: str, seconds: int = 75, style: str = "") -> dict[str, Any]:
    import anthropic

    words = int(seconds * WORDS_PER_SEC)
    prompt = (
        f"Write a faceless short-form video (TikTok/Reels/Shorts, 9:16) about: {topic}\n"
        f"Target about {seconds} seconds of narration (~{words} words). Open with a hook that makes "
        "people stay in the first 2 seconds, deliver concrete value, and end with a payoff or call to action. "
        "Split it into 6-10 scenes of one or two spoken sentences each. For each scene give: text (the exact "
        "narration), kind ('stock' for stock footage or 'text' for a bold animated headline card; use 'text' "
        "for key points and lists), visual (2-4 concrete words to search a stock-video site, e.g. 'coffee "
        "pouring close up'), and headline (max 5 words, for text cards). Write plain spoken English: no "
        "emojis, hashtags or stage directions in the narration."
        + (f"\nStyle notes: {style}" if style else "")
    )
    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=os.environ.get("CLIPSUITE_CLAUDE_MODEL", "claude-opus-5-5"),
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined this topic. Try rephrasing it, or write the script yourself.")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def write_template(topic: str) -> Path:
    path = WORKSPACE / "_drafts" / f"{slugify(topic, 40)}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(TEMPLATE.format(title=topic, query=keywords(topic)))
    return path


# --------------------------------------------------------------------------- voice

_kokoro_pipes: dict[str, Any] = {}


def tts_backends() -> list[str]:
    found = []
    if importlib.util.find_spec("kokoro") and importlib.util.find_spec("soundfile"):
        found.append("kokoro")
    if platform.system() == "Darwin" and shutil.which("say"):
        found.append("say")
    if shutil.which("espeak-ng"):
        found.append("espeak")
    return found


def synthesize(text: str, out_wav: Path, voice: str = "", backend: str = "auto") -> Path:
    """Speak `text` into a 48 kHz mono wav (with a short breath of silence at the end)."""
    backends = tts_backends()
    if backend == "auto":
        if not backends:
            raise RuntimeError("No text-to-speech engine. On a Mac run: pip install 'kokoro>=0.9.4' soundfile "
                               "(or it will use the built-in `say` voice).")
        backend = backends[0]
    tmp = out_wav.with_suffix(".tts" + (".aiff" if backend == "say" else ".wav"))
    if backend == "kokoro":
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline  # type: ignore

        voice = voice or "af_heart"
        lang = voice[0] if voice[0] in "abefhijpz" else "a"
        if lang not in _kokoro_pipes:
            _kokoro_pipes[lang] = KPipeline(lang_code=lang)
        chunks = []
        for result in _kokoro_pipes[lang](text, voice=voice):
            audio = result[2] if isinstance(result, tuple) else getattr(result, "audio", None)
            if audio is None:
                continue
            chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for: {text[:60]}")
        sf.write(str(tmp), np.concatenate(chunks), 24000)
    elif backend == "say":
        cmd = ["say", "-o", tmp, text]
        if voice and not re.fullmatch(r"[a-z]{2}_\w+", voice):  # ignore Kokoro voice names
            cmd[1:1] = ["-v", voice]
        run(cmd, quiet=True)
    elif backend == "espeak":
        run(["espeak-ng", "-s", "165", "-w", tmp, text], quiet=True)
    else:
        raise ValueError(f"Unknown TTS backend {backend!r}")
    run(["ffmpeg", "-y", "-i", tmp, "-af", "apad=pad_dur=0.25", "-ar", "48000", "-ac", "1", out_wav], quiet=True)
    tmp.unlink(missing_ok=True)
    return out_wav


# --------------------------------------------------------------------------- visuals

def pexels_pick(query: str, api_key: str, used: set[int]) -> dict[str, Any] | None:
    """Best portrait video for `query` on Pexels (free API key: pexels.com/api)."""
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "size": "medium", "per_page": 10})
    req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "ClipSuite/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    for v in data.get("videos", []):
        if v["id"] in used:
            continue
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")]
        if not files:
            continue
        # portrait, closest to 1080 wide without going below 720 if possible
        files.sort(key=lambda f: (f["height"] < f["width"], abs(f["width"] - 1080)))
        used.add(v["id"])
        return {"id": v["id"], "link": files[0]["link"], "credit": v.get("user", {}).get("name", ""),
                "page": v.get("url", "")}
    return None


def fetch(url: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".mp4")
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "ClipSuite/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r, dest.with_suffix(".part").open("wb") as f:
            shutil.copyfileobj(r, f)
        dest.with_suffix(".part").replace(dest)
    return dest


def stock_segment(src: Path, dur: float, out: Path) -> Path:
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
          f"format=yuv420p")
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}", "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out], quiet=True)
    return out


def text_segment(headline: str, dur: float, out: Path, accent: str, idx: int) -> Path:
    """Animated headline card: drifting gradient + ASS title (libass)."""
    palettes = [("0x0f2027", "0x2c5364"), ("0x1a1a2e", "0x6a1b9a"), ("0x232526", "0x414345"),
                ("0x141e30", "0x243b55"), ("0x200122", "0x6f0000")]
    c0, c1 = palettes[idx % len(palettes)]
    ass = out.with_suffix(".ass")
    ass.write_text(captions.build_headline_ass(headline, dur, W, H, accent))
    src = (f"gradients=s={W}x{H}:c0={c0}:c1={c1}:x0=0:y0=0:x1={W}:y1={H}:speed=0.012:d={dur:.3f}:r={FPS}")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-vf", f"ass={ass.name},format=yuv420p", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out.name], cwd=out.parent, quiet=True)
    return out


# --------------------------------------------------------------------------- build

def build(plan: dict[str, Any], job: Path | None = None, voice: str = "", tts: str = "auto",
          music: str | None = None, preset: str = "bold", accent: str = "#FFE500") -> Path:
    require("ffmpeg")
    if job is None:
        job = new_job(plan["title"])
    meta = read_json(job / "job.json", {}) or {"id": job.name, "title": plan["title"], "source": "clipsuite create",
                                                "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    write_json(job / "job.json", {**meta, "status": "creating", "error": None})
    try:
        return _build(plan, job, voice, tts, music, preset, accent)
    except Exception as e:
        set_status(job, "error", error=str(e))
        raise


def _build(plan: dict[str, Any], job: Path, voice: str, tts: str, music: str | None, preset: str,
           accent: str) -> Path:
    work = job / "create"
    work.mkdir(parents=True, exist_ok=True)
    plan["voice"] = voice or plan.get("voice", "")
    if music:
        plan["music"] = str(Path(music).expanduser().resolve())
    write_json(job / "plan.json", plan)

    api_key = get_setting("pexels_api_key")
    used: set[int] = set()
    credits, seg_files, voice_files, transcript_segs = [], [], [], []
    t = 0.0
    for i, scene in enumerate(plan["scenes"]):
        n = f"{i + 1:02d}"
        print(f"Scene {n}/{len(plan['scenes'])}: {scene['text'][:60]}", flush=True)
        wav = work / f"voice-{n}.wav"
        key = hashlib.sha1(f"{scene['text']}|{plan.get('voice')}|{tts}".encode()).hexdigest()[:10]
        stamp = work / f"voice-{n}.key"
        if not wav.exists() or not stamp.exists() or stamp.read_text() != key:
            synthesize(scene["text"], wav, plan.get("voice", ""), tts)
            stamp.write_text(key)
        dur = probe(wav)["duration"]

        seg = work / f"scene-{n}.mp4"
        kind = scene.get("kind", "stock")
        if kind == "stock":
            pick = None
            if api_key:
                try:
                    pick = pexels_pick(scene.get("visual") or keywords(scene["text"]), api_key, used)
                except Exception as e:
                    print(f"  ! Pexels search failed ({e}); using a title card", flush=True)
            elif i == 0:
                print("  (no Pexels key: using title cards. Get a free key at pexels.com/api, then run "
                      "`clipsuite config pexels_api_key YOUR_KEY`)", flush=True)
            if pick:
                stock_segment(fetch(pick["link"], WORKSPACE / "_stock"), dur, seg)
                credits.append(f"Scene {n}: video by {pick['credit']} on Pexels {pick['page']}")
                scene["stock_id"] = pick["id"]
            else:
                kind = "text"
        if kind == "text":
            text_segment(scene.get("headline") or _short(scene["text"], 6).upper(), dur, seg, accent, i)
        seg_files.append(seg)
        voice_files.append(wav)
        transcript_segs.append({"start": round(t, 3), "end": round(t + dur, 3), "text": scene["text"]})
        t += dur

    # stitch picture and voice
    _concat(seg_files, work / "visuals.mp4", work / "visuals.txt", copy=True)
    _concat(voice_files, work / "voice.wav", work / "voice.txt", copy=False)
    src = job / "source.mp4"
    if plan.get("music") and Path(plan["music"]).exists():
        fc = ("[2:a]volume=0.18,aresample=48000[m];[m][1:a]sidechaincompress=threshold=0.03:ratio=6:"
              "attack=20:release=400[duck];[1:a][duck]amix=inputs=2:duration=first:normalize=0[a]")
        run(["ffmpeg", "-y", "-i", work / "visuals.mp4", "-i", work / "voice.wav", "-stream_loop", "-1",
             "-i", plan["music"], "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-shortest", src])
    else:
        run(["ffmpeg", "-y", "-i", work / "visuals.mp4", "-i", work / "voice.wav", "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", src])
    (job / "credits.txt").write_text("\n".join(credits) + ("\n" if credits else ""))
    _write_meta(job, title=plan["title"], source="clipsuite create")
    set_status(job, "rendering")
    write_json(job / "plan.json", plan)

    # word timings: Whisper on the clean voice track, else spread words over each scene
    for stale in ("transcript.json", "transcript.srt", "audio.wav"):
        (job / stale).unlink(missing_ok=True)
    if transcribe.available_backends():
        run(["ffmpeg", "-y", "-i", work / "voice.wav", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             job / "audio.wav"], quiet=True)
        transcribe.transcribe(job)
    else:
        write_json(job / "transcript.json", transcribe.clean({"language": "en", "segments": [
            dict(s, words=[]) for s in transcript_segs]}))

    total = round(t, 3)
    old = {c["id"]: c for c in read_json(job / "clips.json", []) or []}
    cid = f"01-{slugify(plan['title'], 32)}"
    clip = {"id": cid, "start": 0.0, "end": total, "title": plan["title"],
            "hook": plan["scenes"][0]["text"], "score": 0, "reason": "made with clipsuite create",
            "style": {"reframe": "crop", "preset": preset, **old.get(cid, {}).get("style", {})},
            "broll_prompts": [], "picker": "create"}
    write_json(job / "clips.json", [clip])
    render.render_all(job)
    set_status(job, "done", error=None)
    print(f"\nDone: {job / 'clips' / cid / 'final.mp4'}  ({total:.0f}s)")
    if total < 61:
        print("Note: under 61s. TikTok's Creator Rewards only pays for videos over 1 minute.")
    return job


def _concat(files: list[Path], out: Path, listfile: Path, copy: bool) -> Path:
    listfile.write_text("".join(f"file '{f.resolve()}'\n" for f in files))
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile]
    cmd += ["-c", "copy"] if copy else ["-c:a", "pcm_s16le"]
    run(cmd + [out], quiet=True)
    return out


def rebuild(job: Path, **kw: Any) -> Path:
    plan = read_json(job / "plan.json")
    if not plan:
        raise RuntimeError(f"{job.name} wasn't made with `clipsuite create` (no plan.json).")
    return build(plan, job=job, voice=kw.pop("voice", "") or plan.get("voice", ""), **kw)

