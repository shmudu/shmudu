"""`clipsuite create --style cartoon`: a story series with your own characters.

Each scene's narration is voiced (Kokoro), and Remotion animates your character
sprites over a background with colour-keyword captions, an on-screen progress
HUD, banners, sticky notes and a "comment one word" vote card.

Script directions (on lines starting with ">" under a scene):

  > scene: bedroom                 background: built-in bedroom / gym / plain, or one you added
  > show: dave-before left, girl right flip enter
                                   characters (names you added with `clipsuite character add`)
                                   position: left / center / right / 0.0-1.0
                                   size: tiny / small / big / huge;  flip;  closeup (mid-shot,
                                   for art that's cut off at the legs);
                                   motion: enter (slide in), bounce, shake, glow (transformation flash), still
  > voice: af_bella                who's speaking this scene (Kokoro voice), default is the narrator
  > hud: EPISODE=1, GLOW-UP=0%     progress boxes along the top (stay until changed; "none" clears)
  > banner: 30 DAYS TO WIN HER     title banner for this scene
  > note: NO.                      sticky-note gag for this scene
  > vote: GYM | Lift heavy. / DIET | No more energy drinks.
                                   split-screen "comment one word" end card

Colour words in the narration: *word* is yellow, {red word}, {blue two words}, {green ...},
{pink ...}, {purple ...}, {orange ...}. Background, cast and HUD carry over to the next
scene until you change them.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import Any

from . import characters, create, transcribe
from .download import new_job
from .pipeline import set_status
from .remotion import REMOTION_DIR, remotion_cmd
from .util import probe, read_json, require, run, slugify, write_json

BUILTIN_BG = {"bedroom", "gym", "plain"}
POSITIONS = {"far-left": 0.18, "left": 0.3, "center": 0.5, "centre": 0.5, "middle": 0.5, "right": 0.7,
             "far-right": 0.82}
SIZES = {"tiny": 0.4, "small": 0.5, "big": 0.72, "huge": 0.82}
MOTIONS = {"enter", "bounce", "shake", "glow", "still"}
ONE_SHOT = {"enter", "shake", "glow"}  # only on the scene where they're written

TEMPLATE = """# {title}
Meet *Dave*. Thirty days to become the man of her {red dark} fantasies. This is day one.
> scene: bedroom
> show: dave-before center enter
> hud: EPISODE=1, GLOW-UP=0%
> banner: 30 DAYS TO WIN HER

She only wants one thing: a man in a {purple mask}.
> show: girl center enter
> voice: af_bella

He opens the fridge. One {green energy drink} and a note that just says {red NO}.
> show: dave-before center shake
> note: NO.

So he goes to the {red gym}. For the first time. Ever.
> scene: gym
> show: dave-before left bounce

What should Dave fix first? Comment one word.
> vote: GYM | Lift heavy. Daily. / DIET | No more energy drinks.

# Tips: add your characters first, e.g. clipsuite character add dave-before art.png --part left
# Colour words with *yellow* or {red words}. ~170-230 words = 65-90 seconds.
"""


# --------------------------------------------------------------------------- parsing

def parse_cast(value: str) -> list[dict[str, Any]]:
    members = []
    for part in value.split(","):
        toks = part.split()
        if not toks:
            continue
        m: dict[str, Any] = {"name": toks[0], "x": None, "height": 0.62, "flip": False, "anim": []}
        for t in (t.lower() for t in toks[1:]):
            if t in POSITIONS:
                m["x"] = POSITIONS[t]
            elif re.fullmatch(r"0?\.\d+|1(\.0+)?|0", t):
                m["x"] = float(t)
            elif t in SIZES:
                m["height"] = SIZES[t]
            elif t == "flip":
                m["flip"] = True
            elif t == "closeup":  # mid-shot: bottom edge below the frame, for art cut off at the legs
                m["closeup"] = True
                m["height"] = max(m["height"], 0.74)
            elif t in MOTIONS:
                m["anim"].append(t)
        members.append(m)
    spread = {1: [0.5], 2: [0.3, 0.7], 3: [0.2, 0.5, 0.8]}.get(len(members), None)
    for i, m in enumerate(members):
        if m["x"] is None:
            m["x"] = spread[i] if spread else (i + 0.5) / len(members)
    return members


def parse_hud(value: str) -> list[dict[str, str]] | None:
    if value.strip().lower() in ("none", "off", "clear"):
        return None
    items = []
    for part in value.split(","):
        label, _, val = part.partition("=")
        if label.strip():
            v = val.strip()
            items.append({"label": label.strip().upper(), "value": v,
                          "color": "#46D160" if v.endswith("%") else "#FFD60A"})
    return items


def parse_vote(value: str) -> dict[str, dict[str, str]]:
    sides = [s.strip() for s in value.split("/", 1)]
    if len(sides) != 2:
        raise ValueError(f"vote needs two sides separated by '/': {value!r}")
    out = {}
    for key, side in zip(("a", "b"), sides):
        title, _, sub = side.partition("|")
        out[key] = {"title": title.strip().upper(), "sub": sub.strip()}
    return out


# --------------------------------------------------------------------------- words

def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def color_words(words: list[dict[str, Any]], tokens: list[tuple[str, str | None]]) -> list[dict[str, Any]]:
    """Copy colours from the script onto Whisper's words (they may differ slightly)."""
    a = [_norm(w["w"]) for w in words]
    b = [_norm(t) for t, _ in tokens]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            color = tokens[blk.b + k][1]
            if color:
                words[blk.a + k]["color"] = color
    return words


def spread_words(tokens: list[tuple[str, str | None]], start: float, end: float) -> list[dict[str, Any]]:
    """No Whisper: space a scene's words across its voice line, weighted by length."""
    if not tokens:
        return []
    speak_end = max(start + 0.2, end - 0.25)  # the voice clip ends with ~0.25s of silence
    weights = [len(t) + 2 for t, _ in tokens]
    total, t, out = sum(weights), start, []
    for (w, c), wt in zip(tokens, weights):
        d = (speak_end - start) * wt / total
        word = {"w": w, "start": round(t, 3), "end": round(t + d, 3)}
        if c:
            word["color"] = c
        out.append(word)
        t += d
    return out


# --------------------------------------------------------------------------- build

def build(plan: dict[str, Any], job: Path | None = None, voice: str = "", tts: str = "auto",
          music: str | None = None, **_: Any) -> Path:
    require("ffmpeg")
    require("npx", "Install Node.js 22+ (brew install node).")
    if job is None:
        job = new_job(plan["title"])
    meta = read_json(job / "job.json", {}) or {"id": job.name, "title": plan["title"], "source": "clipsuite create",
                                                "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    write_json(job / "job.json", {**meta, "status": "creating", "error": None, "style": "cartoon"})
    try:
        return _build(plan, job, voice, tts, music)
    except Exception as e:
        set_status(job, "error", error=str(e))
        raise


def _build(plan: dict[str, Any], job: Path, voice: str, tts: str, music: str | None) -> Path:
    plan["style"] = "cartoon"
    plan["voice"] = voice or plan.get("voice", "")
    if music:
        plan["music"] = str(Path(music).expanduser().resolve())
    write_json(job / "plan.json", plan)
    work = job / "create"
    work.mkdir(parents=True, exist_ok=True)
    public_rel = f"cs/{job.name}"
    public = REMOTION_DIR / "public" / public_rel
    if public.exists():
        shutil.rmtree(public)
    public.mkdir(parents=True)

    def asset(kind: str, name: str) -> str:
        directory = characters.char_dir() if kind == "char" else characters.bg_dir()
        src = characters.find(directory, name)
        if not src:
            return ""
        dest = public / f"{kind}-{src.name}"
        if not dest.exists():
            shutil.copy2(src, dest)
        return f"{public_rel}/{dest.name}"

    missing: set[str] = set()
    scenes_out, voice_files, words = [], [], []
    background, cast, hud = "bedroom", [], None
    t = 0.0
    for i, sc in enumerate(plan["scenes"]):
        n = f"{i + 1:02d}"
        spoken = create.plain_text(sc["text"])
        print(f"Scene {n}/{len(plan['scenes'])}: {spoken[:60]}", flush=True)
        v = sc.get("voice") if isinstance(sc.get("voice"), str) else ""
        v = v or plan["voice"]
        wav = work / f"voice-{n}.wav"
        key = hashlib.sha1(f"{spoken}|{v}|{tts}".encode()).hexdigest()[:10]
        stamp = work / f"voice-{n}.key"
        if not wav.exists() or not stamp.exists() or stamp.read_text() != key:
            create.synthesize(spoken, wav, v, tts)
            stamp.write_text(key)
        dur = probe(wav)["duration"]
        voice_files.append(wav)

        bg_name = sc.get("scene") or sc.get("background") or sc.get("bg")
        if isinstance(bg_name, str) and bg_name:
            custom = asset("bg", bg_name)
            if custom:
                background = custom
            elif bg_name in BUILTIN_BG:
                background = bg_name
            else:
                missing.add(f"background '{bg_name}'")
                background = "plain"
        if isinstance(sc.get("show"), str):
            cast = parse_cast(sc["show"])
        else:  # carry the cast over, without one-shot motions
            cast = [dict(m, anim=[a for a in m["anim"] if a not in ONE_SHOT]) for m in cast]
        out_cast = []
        for m in cast:
            sprite = asset("char", m["name"])
            if not sprite:
                missing.add(f"character '{m['name']}'")
            out_cast.append({**m, "sprite": sprite})
        if isinstance(sc.get("hud"), str):
            hud = parse_hud(sc["hud"])

        scene_out: dict[str, Any] = {"start": round(t, 3), "end": round(t + dur, 3), "background": background,
                                     "cast": out_cast}
        if hud:
            scene_out["hud"] = hud
        for k in ("banner", "note"):
            if isinstance(sc.get(k), str) and sc[k]:
                scene_out[k] = sc[k]
        if isinstance(sc.get("vote"), str):
            scene_out["vote"] = parse_vote(sc["vote"])
        scenes_out.append(scene_out)
        words += spread_words(create.script_tokens(sc["text"]), t, t + dur)
        t += dur
    total = round(t, 3)
    if missing:
        print("  ! Not found, using placeholders: " + ", ".join(sorted(missing)) +
              "\n    Add them with: clipsuite character add NAME image.png  /  clipsuite background add NAME image.png",
              flush=True)

    # audio: voice, plus optional ducked music
    create._concat(voice_files, work / "voice.wav", work / "voice.txt", copy=False)
    audio = public / "audio.wav"
    if plan.get("music") and Path(plan["music"]).exists():
        fc = ("[1:a]volume=0.18,aresample=48000[m];[m][0:a]sidechaincompress=threshold=0.03:ratio=6:"
              "attack=20:release=400[duck];[0:a][duck]amix=inputs=2:duration=first:normalize=0,"
              "loudnorm=I=-14:TP=-1.5[a]")
        run(["ffmpeg", "-y", "-i", work / "voice.wav", "-stream_loop", "-1", "-i", plan["music"],
             "-filter_complex", fc, "-map", "[a]", "-ar", "48000", audio], quiet=True)
    else:
        run(["ffmpeg", "-y", "-i", work / "voice.wav", "-af", "loudnorm=I=-14:TP=-1.5", "-ar", "48000", audio],
            quiet=True)

    # word timings: Whisper when available (more exact), coloured from the script
    for stale in ("transcript.json", "transcript.srt", "audio.wav"):
        (job / stale).unlink(missing_ok=True)
    if transcribe.available_backends():
        run(["ffmpeg", "-y", "-i", work / "voice.wav", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             job / "audio.wav"], quiet=True)
        tr = transcribe.transcribe(job, force=True)
        all_tokens = [tok for sc in plan["scenes"] for tok in create.script_tokens(sc["text"])]
        words = color_words(transcribe.all_words(tr), all_tokens)
    else:
        write_json(job / "transcript.json", {"language": "en", "segments": [
            {"start": s["start"], "end": s["end"], "text": create.plain_text(p["text"]),
             "words": [w for w in words if s["start"] <= w["start"] < s["end"]]}
            for s, p in zip(scenes_out, plan["scenes"])]})

    props = {"audioFile": f"{public_rel}/audio.wav", "durationInSeconds": total, "scenes": scenes_out,
             "words": words, "wordsPerLine": int(plan.get("words_per_line", 2)), "captionPosition": 0.66}
    cid = f"01-{slugify(plan['title'], 32)}"
    out_dir = job / "clips" / cid
    out_dir.mkdir(parents=True, exist_ok=True)
    props_path = write_json(out_dir / "cartoon-props.json", props)
    set_status(job, "rendering")
    final = out_dir / "final.mp4"
    print(f"Rendering {total:.0f}s cartoon with Remotion (this takes a few minutes)...", flush=True)
    run(remotion_cmd("CartoonShort", final, props_path), cwd=REMOTION_DIR)
    shutil.copy2(final, job / "source.mp4")  # lets the usual tools (Resolve export, re-cuts) use it
    run(["ffmpeg", "-y", "-ss", "1", "-i", final.name, "-frames:v", "1", "-vf", "scale=360:-2", "thumb.jpg"],
        cwd=out_dir, quiet=True)
    clip = {"id": cid, "start": 0.0, "end": total, "title": plan["title"], "hook": create.plain_text(plan["scenes"][0]["text"]),
            "score": 0, "reason": "made with clipsuite create --style cartoon", "style": {}, "broll_prompts": [],
            "picker": "create", "render": {"final": str(final), "duration": total}}
    write_json(job / "clips.json", [clip])
    meta = read_json(job / "job.json", {})
    meta.update(media=probe(final), status="done", error=None)
    write_json(job / "job.json", meta)
    print(f"\nDone: {final}  ({total:.0f}s)")
    if total < 61:
        print("Note: under 61s. TikTok's Creator Rewards only pays for videos over 1 minute.")
    return job


def write_template(topic: str, path: Path | None = None) -> Path:
    from .util import WORKSPACE

    path = path or WORKSPACE / "_drafts" / f"{slugify(topic, 40)}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(TEMPLATE.replace("{title}", topic))
    return path

