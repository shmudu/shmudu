"""Runs inside .venv-chatterbox (see setup/install_chatterbox.sh); ClipSuite calls it with a
JSON file of jobs: [{"text", "out", "voice", "exaggeration", "cfg_weight"}, ...].
The model loads once, then every line is spoken. Standalone on purpose: no clipsuite imports."""

import json
import sys

import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS


def load():
    if torch.backends.mps.is_available():
        try:
            return ChatterboxTTS.from_pretrained(device="mps"), "mps"
        except Exception as e:  # some PyTorch builds still trip on MPS
            print(f"  (Apple GPU not usable here: {e}; using CPU)", flush=True)
    return ChatterboxTTS.from_pretrained(device="cpu"), "cpu"


def main(path):
    jobs = json.load(open(path))
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
