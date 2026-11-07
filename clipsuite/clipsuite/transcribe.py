"""Speech-to-text with word timestamps using Whisper.

Backends (picked automatically in this order unless --backend is given):
  mlx      mlx-whisper   - fastest on Apple Silicon Macs
  faster   faster-whisper - fast on CPU / NVIDIA
  openai   openai-whisper - the reference implementation
"""

from __future__ import annotations

import importlib.util
import platform
from pathlib import Path
from typing import Any

from .util import read_json, require, run, write_json

DEFAULT_MODELS = {
    "mlx": "mlx-community/whisper-large-v3-turbo",
    "faster": "large-v3-turbo",
    "openai": "turbo",
}


def available_backends() -> list[str]:
    order = []
    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    if is_apple_silicon and importlib.util.find_spec("mlx_whisper"):
        order.append("mlx")
    if importlib.util.find_spec("faster_whisper"):
        order.append("faster")
    if importlib.util.find_spec("whisper"):
        order.append("openai")
    return order


def extract_audio(video: Path, out: Path) -> Path:
    require("ffmpeg", "Install FFmpeg (brew install ffmpeg).")
    if not out.exists():
        run(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out])
    return out


def transcribe(job: Path, backend: str = "auto", model: str | None = None,
               language: str | None = None, force: bool = False) -> dict[str, Any]:
    out_path = job / "transcript.json"
    if out_path.exists() and not force:
        return read_json(out_path)

    audio = extract_audio(job / "source.mp4", job / "audio.wav")
    backends = available_backends()
    if backend == "auto":
        if not backends:
            raise RuntimeError(
                "No Whisper backend installed. On a Mac run: pip install mlx-whisper  "
                "(elsewhere: pip install faster-whisper)"
            )
        backend = backends[0]
    model = model or DEFAULT_MODELS[backend]
    print(f"Transcribing with {backend} ({model})...", flush=True)

    if backend == "mlx":
        import mlx_whisper  # type: ignore

        raw = mlx_whisper.transcribe(str(audio), path_or_hf_repo=model, word_timestamps=True, language=language)
        result = _from_openai_dict(raw)
    elif backend == "faster":
        from faster_whisper import WhisperModel  # type: ignore

        wm = WhisperModel(model, device="auto", compute_type="auto")
        segs, info = wm.transcribe(str(audio), word_timestamps=True, vad_filter=True, language=language)
        result = {"language": info.language, "segments": [
            {
                "start": s.start, "end": s.end, "text": s.text.strip(),
                "words": [{"w": w.word.strip(), "start": w.start, "end": w.end} for w in (s.words or [])],
            }
            for s in segs
        ]}
    elif backend == "openai":
        import whisper  # type: ignore

        raw = whisper.load_model(model).transcribe(str(audio), word_timestamps=True, language=language)
        result = _from_openai_dict(raw)
    else:
        raise ValueError(f"Unknown backend {backend!r}")

    result["backend"], result["model"] = backend, model
    write_json(out_path, clean(result))
    write_srt(result["segments"], job / "transcript.srt")
    return result


def _from_openai_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {"language": raw.get("language"), "segments": [
        {
            "start": s["start"], "end": s["end"], "text": s["text"].strip(),
            "words": [{"w": w["word"].strip(), "start": w["start"], "end": w["end"]} for w in s.get("words", [])],
        }
        for s in raw.get("segments", [])
    ]}


def clean(result: dict[str, Any]) -> dict[str, Any]:
    """Drop empty words, round times and make sure each segment has words."""
    for seg in result["segments"]:
        words = [w for w in seg.get("words", []) if w["w"]]
        if not words and seg["text"]:  # synthesize evenly spaced words
            tokens = seg["text"].split()
            step = (seg["end"] - seg["start"]) / max(len(tokens), 1)
            words = [{"w": t, "start": seg["start"] + i * step, "end": seg["start"] + (i + 1) * step}
                     for i, t in enumerate(tokens)]
        for w in words:
            w["start"], w["end"] = round(w["start"], 3), round(max(w["end"], w["start"] + 0.05), 3)
        seg["words"] = words
        seg["start"], seg["end"] = round(seg["start"], 3), round(seg["end"], 3)
    return result


def all_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    return [w for s in transcript["segments"] for w in s["words"]]


def write_srt(segments: list[dict[str, Any]], path: Path, offset: float = 0.0) -> Path:
    from .util import fmt_ts

    lines = []
    for i, s in enumerate(segments, 1):
        lines += [str(i), f"{fmt_ts(s['start'] - offset)} --> {fmt_ts(s['end'] - offset)}", s["text"], ""]
    path.write_text("\n".join(lines))
    return path
