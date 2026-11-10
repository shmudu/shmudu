"""Narration: which engine speaks, how names are pronounced, and whose voice it is.

Engines (best first, `--tts auto` picks the first one installed):
  chatterbox  Resemble AI's open-source model: expressive, natural pacing, can copy a voice
              from a 10-30 second sample. Installed in its own environment by
              setup/install_chatterbox.sh (its pinned PyTorch would clash with Kokoro).
  kokoro      small and fast; af_heart / af_bella are its most natural voices.
  say         macOS built-in voices (download "Premium" ones in System Settings).

  clipsuite pronounce Saito "Sigh-toh"      fix how a name is read (all engines)
  clipsuite voice add narrator me.wav        save a voice sample for Chatterbox
  > voice: narrator                          ...and use it for a scene
  > emotion: 0.8                             Chatterbox expressiveness for a scene (0.3 calm - 1.5 intense)
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from . import create, util
from .util import read_json, run, write_json

ROOT = Path(__file__).resolve().parent.parent
CHATTERBOX_PY = ROOT / ".venv-chatterbox" / "bin" / "python"
WORKER = Path(__file__).resolve().parent / "chatterbox_worker.py"


# --------------------------------------------------------------------------- pronunciation

def pronunciations() -> dict[str, str]:
    return dict(read_json(util.CONFIG_FILE, {}).get("pronounce", {}) or {})


def set_pronunciation(word: str, say_as: str | None) -> dict[str, str]:
    data = read_json(util.CONFIG_FILE, {}) or {}
    table = dict(data.get("pronounce", {}) or {})
    if say_as:
        table[word] = say_as
    else:
        table.pop(word, None)
    data["pronounce"] = table
    write_json(util.CONFIG_FILE, data)
    return table


def apply_pronunciations(text: str) -> str:
    for word, say_as in sorted(pronunciations().items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", say_as, text, flags=re.IGNORECASE)
    return text


# --------------------------------------------------------------------------- voice samples

def voices_dir() -> Path:
    return util.WORKSPACE / "_voices"


def add_voice(name: str, src: Path) -> Path:
    """Save a clean 24 kHz mono sample (max 30 s) for Chatterbox to imitate."""
    voices_dir().mkdir(parents=True, exist_ok=True)
    dest = voices_dir() / f"{name}.wav"
    run(["ffmpeg", "-y", "-i", Path(src).expanduser(), "-t", "30", "-ac", "1", "-ar", "24000",
         "-af", "silenceremove=start_periods=1:start_threshold=-45dB,loudnorm=I=-18", dest], quiet=True)
    return dest


def sample_for(voice: str) -> str:
    """A Chatterbox reference: a saved sample name, or a path to an audio file."""
    if not voice:
        return ""
    named = voices_dir() / f"{voice}.wav"
    if named.exists():
        return str(named)
    p = Path(voice).expanduser()
    return str(p) if p.suffix.lower() in (".wav", ".mp3", ".m4a", ".flac", ".aiff") and p.exists() else ""


# --------------------------------------------------------------------------- engines

def chatterbox_installed() -> bool:
    return CHATTERBOX_PY.exists()


def pick_backend(tts: str) -> str:
    if tts != "auto":
        if tts == "chatterbox" and not chatterbox_installed():
            raise RuntimeError("Chatterbox isn't installed. Run: bash setup/install_chatterbox.sh")
        return tts
    if chatterbox_installed():
        return "chatterbox"
    found = create.tts_backends()
    return found[0] if found else "auto"  # synthesize() explains how to install an engine


def scene_lines(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """One narration line per scene: plain text, the scene's voice (or the plan's) and emotion."""
    lines = []
    for sc in plan["scenes"]:
        v = sc.get("voice") if isinstance(sc.get("voice"), str) else ""
        lines.append({"text": create.plain_text(sc["text"]), "voice": v or plan.get("voice", ""),
                      "emotion": sc.get("emotion") if isinstance(sc.get("emotion"), str) else None})
    return lines


def voice_lines(lines: list[dict[str, Any]], work: Path, tts: str = "auto") -> list[Path]:
    """Voice every line (dicts with text, voice, emotion) into work/voice-NN.wav.

    Lines whose text, voice, engine and pronunciation haven't changed are reused.
    """
    backend = pick_backend(tts)
    todo, wavs = [], []
    for i, line in enumerate(lines):
        spoken = apply_pronunciations(line["text"])
        wav = work / f"voice-{i + 1:02d}.wav"
        key = hashlib.sha1(json.dumps([spoken, line.get("voice", ""), line.get("emotion"), backend]).encode()).hexdigest()[:12]
        stamp = work / f"voice-{i + 1:02d}.key"
        wavs.append(wav)
        if not (wav.exists() and stamp.exists() and stamp.read_text() == key):
            todo.append((spoken, wav, line, stamp, key))
    if not todo:
        return wavs
    print(f"Voicing {len(todo)} line(s) with {backend}...", flush=True)
    if backend == "chatterbox":
        _chatterbox_batch(todo, work)
    else:
        for spoken, wav, line, stamp, key in todo:
            v = line.get("voice", "")
            if backend == "kokoro" and not re.fullmatch(r"[a-z]{2}_\w+", v):
                v = ""  # a Chatterbox sample name means nothing to Kokoro: use its default voice
            create.synthesize(spoken, wav, v, backend)
            stamp.write_text(key)
    return wavs


def _chatterbox_batch(todo: list, work: Path) -> None:
    jobs = []
    for spoken, wav, line, _stamp, _key in todo:
        emotion = line.get("emotion")
        try:
            exaggeration = float(emotion) if emotion not in (None, "", True) else 0.55
        except ValueError:
            exaggeration = 0.55
        jobs.append({"text": spoken, "out": str(wav.with_suffix(".cb.wav")), "voice": sample_for(line.get("voice", "")),
                     # stronger emotion speeds speech up; lower cfg keeps the pacing natural
                     "exaggeration": max(0.25, min(2.0, exaggeration)),
                     "cfg_weight": 0.5 if exaggeration <= 0.6 else 0.35})
    jobs_file = write_json(work / "chatterbox-jobs.json", jobs)
    proc = subprocess.run([str(CHATTERBOX_PY), str(WORKER), str(jobs_file)], text=True)
    if proc.returncode != 0:
        raise RuntimeError("Chatterbox failed (see the messages above). Try again, or use --tts kokoro.")
    for (spoken, wav, line, stamp, key), job in zip(todo, jobs):
        tmp = Path(job["out"])
        run(["ffmpeg", "-y", "-i", tmp, "-af", "apad=pad_dur=0.2", "-ar", "48000", "-ac", "1", wav], quiet=True)
        tmp.unlink(missing_ok=True)
        stamp.write_text(key)
