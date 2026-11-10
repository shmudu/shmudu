"""Runs inside .venv-chatterbox (see setup/install_chatterbox.sh); ClipSuite calls it with a
JSON file of jobs: [{"text", "out", "voice", "exaggeration", "cfg_weight"}, ...].
The model loads once, then every line is spoken. Standalone on purpose: no clipsuite imports."""

import json
import sys

import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS


def check_watermarker():
    """Chatterbox marks its audio with Resemble's inaudible watermark. If that package can't load
    (usually a missing pkg_resources), say how to fix it instead of failing deep inside Chatterbox."""
    import perth

    if perth.PerthImplicitWatermarker is None:
        try:
            from perth.perth_net.perth_net_implicit.perth_watermarker import PerthImplicitWatermarker  # noqa: F401
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        else:
            reason = "unknown"
        sys.exit(f"Chatterbox's watermarker couldn't load ({reason}).\n"
                 "Fix:  .venv-chatterbox/bin/pip install 'setuptools<81'   then render again.")


def load():
    if torch.backends.mps.is_available():
        try:
            return ChatterboxTTS.from_pretrained(device="mps"), "mps"
        except Exception as e:  # some PyTorch builds still trip on MPS
            print(f"  (Apple GPU not usable here: {type(e).__name__}: {e}; using CPU)", flush=True)
    return ChatterboxTTS.from_pretrained(device="cpu"), "cpu"


def main(path):
    jobs = json.load(open(path))
    check_watermarker()
    model, device = load()
    print(f"  Chatterbox loaded on {device}", flush=True)
    for i, job in enumerate(jobs, 1):
        kwargs = {"exaggeration": job.get("exaggeration", 0.5), "cfg_weight": job.get("cfg_weight", 0.5)}
        if job.get("voice"):
            kwargs["audio_prompt_path"] = job["voice"]
        try:
            wav = model.generate(job["text"], **kwargs)
        except Exception as e:
            if device == "cpu":
                raise
            print(f"  (GPU error: {e}; retrying on CPU)", flush=True)
            model, device = ChatterboxTTS.from_pretrained(device="cpu"), "cpu"
            wav = model.generate(job["text"], **kwargs)
        ta.save(job["out"], wav, model.sr)
        print(f"  line {i}/{len(jobs)} done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
