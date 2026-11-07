"""Tests that run without Whisper or network: a synthetic video plus a hand-made transcript."""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SENTENCES = [
    "Why do most people never save any money at all?",
    "Here is the secret nobody tells you about budgeting.",
    "You pay yourself first, before rent, before anything else.",
    "I learned this the hard way after my biggest mistake.",
    "Um so like anyway that was kind of a long time ago.",
    "The rule is simple: automate ten percent on payday.",
    "Stop waiting for motivation and set it up today.",
    "That's honestly the whole trick, and it works.",
]


def make_transcript(seconds_per: float = 4.0) -> dict:
    segs, t = [], 0.0
    for s in SENTENCES:
        words = s.split()
        step = seconds_per / len(words)
        segs.append({"start": t, "end": t + seconds_per, "text": s,
                     "words": [{"w": w, "start": round(t + i * step, 3), "end": round(t + (i + 1) * step, 3)}
                               for i, w in enumerate(words)]})
        t += seconds_per
    return {"language": "en", "segments": segs}


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSUITE_WORKSPACE", str(tmp_path / "workspace"))
    import clipsuite.util as util
    importlib.reload(util)
    for m in ("download", "transcribe", "highlights", "captions", "render", "resolve", "chatcut", "wan2gp", "pipeline"):
        importlib.reload(importlib.import_module(f"clipsuite.{m}"))
    return tmp_path


def test_heuristic_picks_non_overlapping_clips():
    from clipsuite import highlights

    clips = highlights.heuristic(make_transcript(), count=2, min_len=8, max_len=14)
    assert 1 <= len(clips) <= 2
    for a, b in zip(clips, clips[1:]):
        assert a["end"] <= b["start"] + 0.5
    # the question-led money hook should win a slot
    assert any("money" in c["hook"] or "secret" in c["hook"] for c in clips)


def test_captions_ass_and_srt():
    from clipsuite import captions

    words = captions.clip_words([w for s in make_transcript()["segments"] for w in s["words"]], 4.0, 12.0)
    assert words[0]["start"] >= 0 and words[-1]["end"] <= 8.0
    ass = captions.build_ass(words, title="Pay yourself first")
    assert "Style: Cap" in ass and "Dialogue: 1" in ass and "PAY YOURSELF FIRST" not in ass
    assert ass.count("Dialogue: 0") == len(words)
    srt = captions.build_srt(words)
    assert srt.startswith("1\n00:00:00,000 -->")


def test_chunk_breaks_on_sentence_end():
    from clipsuite.captions import chunk

    ws_ = [{"w": "Hi.", "start": 0, "end": .3}, {"w": "Next", "start": .3, "end": .6}, {"w": "one", "start": .6, "end": .9}]
    assert [len(g) for g in chunk(ws_, 5)] == [1, 2]


def test_reframe_crop_is_9x16():
    from clipsuite.render import reframe_filter

    f = reframe_filter("crop", 1920, 1080, 0.5)
    assert f.startswith("crop=608:1080:656:0")
    assert reframe_filter("crop", 1920, 1080, 0.0).startswith("crop=608:1080:0:0")
    assert reframe_filter("crop", 1920, 1080, 1.0).startswith("crop=608:1080:1312:0")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_end_to_end_render_and_exports(ws, tmp_path):
    from clipsuite import chatcut, download, highlights, render, resolve, util, wan2gp

    src = tmp_path / "talk.mp4"
    dur = len(SENTENCES) * 4
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)],
                   check=True, capture_output=True)
    job = download.import_file(src)
    util.write_json(job / "transcript.json", make_transcript())

    clips = highlights.pick(job, picker="heuristic", count=2, min_len=8, max_len=14)
    assert clips and all("id" in c for c in clips)
    # simulate a Wan2GP output and attach it as b-roll
    broll = tmp_path / "broll.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "mandelbrot=size=480x832:rate=16", "-t", "3",
                    "-pix_fmt", "yuv420p", str(broll)], check=True, capture_output=True)
    wan2gp.attach(job, clips[0]["id"], [broll], at=[2.0], duration=2.0)

    render.render_all(job, defaults={"preset": "bold", "reframe": "crop"})
    for c in util.read_json(job / "clips.json"):
        out = job / "clips" / c["id"]
        for name in ("raw.mp4", "final.mp4", "captions.ass", "captions.srt", "thumb.jpg"):
            assert (out / name).exists(), name
        info = util.probe(out / "final.mp4")
        assert (info["width"], info["height"]) == (1080, 1920)
        assert info["has_audio"]
        assert abs(info["duration"] - (c["end"] - c["start"])) < 0.3

    fcp = resolve.export_fcpxml(job)
    root = ET.parse(fcp).getroot()
    assert root.tag == "fcpxml" and len(root.findall(".//project")) == 1 + len(clips)

    z = chatcut.export(job)
    assert z.exists() and (job / "exports" / "chatcut" / clips[0]["id"] / "BRIEF.md").exists()
    assert "Wan2GP" in wan2gp.write_prompts(job).read_text()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_hyperframes_stitch_adds_silent_audio(tmp_path):
    from clipsuite import hyperframes, util

    card = tmp_path / "card.mp4"
    main = tmp_path / "main.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:size=1080x1920:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", str(card)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=duration=2", "-shortest", "-pix_fmt", "yuv420p", str(main)],
                   check=True, capture_output=True)
    out = hyperframes.stitch([card, main, card], tmp_path / "out.mp4")
    info = util.probe(out)
    assert info["has_audio"] and 3.8 < info["duration"] < 4.3

    folder = hyperframes.write_card(tmp_path / "intro", "intro", "A <b> title", "", 1.5, "#FFE500")
    html = (folder / "index.html").read_text()
    assert 'data-composition-id="intro"' in html and "A &lt;b&gt; title" in html and "{{" not in html


def test_cli_doctor_runs(capsys):
    from clipsuite import cli

    cli.main(["doctor"])
    assert "ffmpeg" in capsys.readouterr().out
