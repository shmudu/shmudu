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


def test_broken_opencv_falls_back(monkeypatch, tmp_path, capsys):
    """A half-installed cv2 (no CascadeClassifier) must not crash rendering."""
    import sys
    import types
    from clipsuite import cli, render

    broken = types.ModuleType("cv2")
    monkeypatch.setitem(sys.modules, "cv2", broken)
    monkeypatch.setattr(render.importlib.util, "find_spec", lambda name: object())
    assert render.detect_face_x(tmp_path / "x.mp4", 0, 5) is None
    assert "face tracking unavailable" in capsys.readouterr().out
    assert cli._opencv_ok() is False


def test_render_stops_clearly_without_libass(ws, monkeypatch):
    from clipsuite import render, util

    job = util.job_dir("j1")
    util.write_json(job / "clips.json", [{"id": "c", "start": 0, "end": 5}])
    monkeypatch.setattr(render, "ffmpeg_has_filter", lambda name: False)
    with pytest.raises(util.ToolMissing, match="homebrew-ffmpeg"):
        render.render_all(job)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_ffmpeg_filter_detection():
    from clipsuite.util import ffmpeg_has_filter

    assert ffmpeg_has_filter("scale")
    assert not ffmpeg_has_filter("definitely_not_a_filter")


SCRIPT = """# 3 money habits that changed my life
Most people never save a dollar. Here's what finally worked for me.
> stock: piggy bank coins

Habit one: pay yourself first, the day your paycheck lands.
> text: PAY YOURSELF FIRST

Habit two: automate it, so willpower never enters the picture.

# Tip: this line is ignored
"""


def test_parse_script():
    from clipsuite.create import parse_script

    plan = parse_script(SCRIPT)
    assert plan["title"] == "3 money habits that changed my life"
    kinds = [s["kind"] for s in plan["scenes"]]
    assert kinds == ["stock", "text", "stock"]
    assert plan["scenes"][0]["visual"] == "piggy bank coins"
    assert plan["scenes"][1]["headline"] == "PAY YOURSELF FIRST"
    assert plan["scenes"][2]["visual"]  # auto keywords
    with pytest.raises(ValueError):
        parse_script("# only a title")


def _fake_tts(text, out_wav, voice="", backend="auto"):
    dur = max(1.0, len(text.split()) / 2.6)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}",
                    "-ar", "48000", "-ac", "1", str(out_wav)], check=True, capture_output=True)
    return out_wav


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_create_builds_a_rendered_job(ws, tmp_path, monkeypatch):
    from clipsuite import create, util

    importlib.reload(create)
    stock = tmp_path / "stock.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=25:duration=2",
                    "-pix_fmt", "yuv420p", str(stock)], check=True, capture_output=True)
    monkeypatch.setattr(create, "synthesize", _fake_tts)
    monkeypatch.setattr(create, "get_setting", lambda name, default="": "fake-key" if name == "pexels_api_key" else "")
    monkeypatch.setattr(create, "pexels_pick",
                        lambda q, key, used: {"id": len(used), "link": "x", "credit": "Ann", "page": "p"})
    monkeypatch.setattr(create, "fetch", lambda url, cache: stock)
    monkeypatch.setattr(create.transcribe, "available_backends", lambda: [])

    job = create.build(create.parse_script(SCRIPT))
    clip = util.read_json(job / "clips.json")[0]
    final = job / "clips" / clip["id"] / "final.mp4"
    info = util.probe(final)
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
    assert abs(info["duration"] - clip["end"]) < 0.3
    assert len(util.read_json(job / "transcript.json")["segments"]) == 3
    assert "Ann" in (job / "credits.txt").read_text()

    # edit the plan and rebuild in place: voice cache is reused, scenes change
    plan = util.read_json(job / "plan.json")
    plan["scenes"] = plan["scenes"][:2]
    util.write_json(job / "plan.json", plan)
    create.rebuild(job)
    assert len(util.read_json(job / "transcript.json")["segments"]) == 2


def test_pexels_pick_prefers_portrait(monkeypatch):
    import io
    from clipsuite import create

    payload = {"videos": [{"id": 1, "url": "u1", "user": {"name": "Bo"}, "video_files": [
        {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "landscape"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "portrait-1080"},
        {"file_type": "video/mp4", "width": 540, "height": 960, "link": "portrait-540"}]}]}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    seen = {}
    def fake_open(req, timeout=0):
        seen["auth"] = req.headers.get("Authorization")
        return Resp(json.dumps(payload).encode())
    monkeypatch.setattr(create.urllib.request, "urlopen", fake_open)
    used: set = set()
    pick = create.pexels_pick("coffee", "KEY", used)
    assert pick["link"] == "portrait-1080" and seen["auth"] == "KEY" and used == {1}
    assert create.pexels_pick("coffee", "KEY", used) is None  # no repeats


class _Resp:
    def __init__(self, data): self.data = json.dumps(data).encode()
    def __enter__(self):
        import io
        return io.BytesIO(self.data)
    def __exit__(self, *a): pass


def test_pixabay_pick_prefers_portrait(monkeypatch):
    from clipsuite import create

    payload = {"hits": [
        {"id": 1, "user": "Al", "pageURL": "p1", "videos": {
            "large": {"url": "land-1920", "width": 1920, "height": 1080}}},
        {"id": 2, "user": "Bea", "pageURL": "p2", "videos": {
            "large": {"url": "port-1920", "width": 1080, "height": 1920},
            "small": {"url": "port-640", "width": 360, "height": 640}}}]}
    seen = {}
    def fake_open(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp(payload)
    monkeypatch.setattr(create.urllib.request, "urlopen", fake_open)
    used: set = set()
    pick = create.pixabay_pick("coffee pour", "KEY", used)
    assert pick["link"] == "port-1920" and pick["credit"] == "Bea" and "key=KEY" in seen["url"]
    assert create.pixabay_pick("coffee pour", "KEY", used)["link"] == "land-1920"  # then the next one
    assert create.pixabay_pick("coffee pour", "KEY", used) is None


def test_local_footage_matches_names(tmp_path, monkeypatch):
    from clipsuite import create

    for rel in ("money/piggy-bank.mp4", "city/night-street.mov", "misc/random.mp4", "notes.txt"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    monkeypatch.setattr(create, "get_setting", lambda name, default="": "")
    used: set = set()
    assert create.local_pick("piggy bank coins", tmp_path, used)["path"].name == "piggy-bank.mp4"
    assert create.stock_pick("city night", used, str(tmp_path))["path"].name == "night-street.mov"
    assert create.has_stock_source(str(tmp_path)) and not create.has_stock_source()
    # unused footage first, then repeat the best match; give up if nothing matches at all
    assert create.local_pick("piggy bank", tmp_path, used)["path"].name == "random.mp4"
    assert create.local_pick("piggy bank", tmp_path, used)["path"].name == "piggy-bank.mp4"
    assert create.local_pick("volcano", tmp_path, used) is None


def test_create_missing_script_writes_template(ws, tmp_path):
    from clipsuite import cli

    target = tmp_path / "drafts" / "3-money-habits.txt"
    with pytest.raises(SystemExit) as e:
        cli.main(["create", "--script", str(target)])
    assert "made a template" in str(e.value) and target.exists()
    assert "# 3 money habits" in target.read_text()
    with pytest.raises(SystemExit) as e:  # untouched template is refused, not rendered
        cli.main(["create", "--script", str(target)])
    assert "still has the template text" in str(e.value)


def test_cartoon_directions_parse():
    from clipsuite import cartoon

    cast = cartoon.parse_cast("dave-before left bounce, girl right flip enter")
    assert cast[0] == {"name": "dave-before", "x": 0.3, "height": 0.62, "flip": False, "anim": ["bounce"]}
    assert cast[1]["flip"] and cast[1]["anim"] == ["enter"] and cast[1]["x"] == 0.7
    assert [m["x"] for m in cartoon.parse_cast("a, b")] == [0.3, 0.7]
    assert cartoon.parse_cast("a big 0.4")[0]["height"] == 0.72
    assert cartoon.parse_cast("a closeup")[0]["closeup"] and cartoon.parse_cast("a closeup")[0]["height"] == 0.74
    hud = cartoon.parse_hud("EPISODE=1, glow-up=0%")
    assert hud[1] == {"label": "GLOW-UP", "value": "0%", "color": "#46D160"}
    assert cartoon.parse_hud("none") is None
    vote = cartoon.parse_vote("gym | Lift heavy. / diet | No more cans.")
    assert vote["a"] == {"title": "GYM", "sub": "Lift heavy."} and vote["b"]["title"] == "DIET"


def test_caption_colours_follow_whisper_words():
    from clipsuite import cartoon, create

    tokens = create.script_tokens("One {green energy drink} and a note that says {red NO}.")
    whisper = [{"w": w, "start": i, "end": i + 1} for i, w in
               enumerate("one energy drink and uh a note that says no".split())]
    out = cartoon.color_words(whisper, tokens)
    assert out[1]["color"] == out[2]["color"] == "#46D160"
    assert out[-1]["color"] == "#FF3B30" and "color" not in out[4]
    spread = cartoon.spread_words(tokens, 2.0, 6.0)
    assert spread[0]["start"] == 2.0 and spread[-1]["end"] <= 5.76 and spread[-1]["w"] == "NO."


def test_cut_out_removes_background_and_gaps(tmp_path):
    from PIL import Image, ImageDraw
    from clipsuite import characters

    img = Image.new("RGB", (400, 600), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((100, 100, 300, 500), fill="black")          # body
    d.rectangle((160, 200, 240, 400), fill="white")          # big enclosed gap (arm/body)
    d.rectangle((130, 120, 136, 126), fill="white")          # tiny white detail (an eye)
    src = tmp_path / "c.png"
    img.save(src)
    out = characters.cut_out(src)
    a = out.getchannel("A")
    ox, oy = 100 - 4, 100 - 4  # trimmed to the figure plus padding
    assert out.size == (209, 409)
    assert a.getpixel((200 - ox, 300 - oy)) == 0      # gap cleared
    assert a.getpixel((133 - ox, 123 - oy)) == 255    # small detail kept
    assert a.getpixel((110 - ox, 110 - oy)) == 255    # body kept


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_cartoon_build_pipeline(ws, tmp_path, monkeypatch):
    from PIL import Image
    from clipsuite import cartoon, characters, create, util

    importlib.reload(characters)
    importlib.reload(cartoon)
    Image.new("RGB", (300, 600), "white").save(tmp_path / "dave.png")
    characters.add_character("dave-before", tmp_path / "dave.png", keep_background=True)
    monkeypatch.setattr(create, "synthesize", _fake_tts)
    monkeypatch.setattr(cartoon.transcribe, "available_backends", lambda: [])
    pub = tmp_path / "remotion"
    monkeypatch.setattr(cartoon, "REMOTION_DIR", pub)
    seen = {}

    def fake_cmd(comp, out, props):
        seen["props"] = util.read_json(Path(props))
        seen["comp"] = comp
        dur = seen["props"]["durationInSeconds"]
        return ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=purple:size=1080x1920:rate=30:duration={dur}",
                "-f", "lavfi", "-i", f"sine=duration={dur}", "-shortest", "-pix_fmt", "yuv420p", str(out)]
    monkeypatch.setattr(cartoon, "remotion_cmd", fake_cmd)

    plan = create.parse_script(cartoon.TEMPLATE.replace("{title}", "Day 1"))
    job = cartoon.build(plan)
    props = seen["props"]
    assert seen["comp"] == "CartoonShort" and len(props["scenes"]) == 5
    s = props["scenes"]
    assert s[0]["background"] == "bedroom" and s[0]["cast"][0]["sprite"].endswith("char-dave-before.png")
    assert s[0]["hud"][1]["value"] == "0%" and s[0]["banner"] == "30 DAYS TO WIN HER"
    assert s[1]["cast"][0]["name"] == "girl" and s[1]["cast"][0]["sprite"] == ""   # placeholder
    assert s[2]["note"] == "NO." and "banner" not in s[2] and s[2]["hud"]            # hud carries over
    assert s[3]["background"] == "gym" and s[4]["vote"]["a"]["title"] == "GYM"
    assert s[4]["cast"][0]["anim"] == ["bounce"]                                     # one-shots dropped
    assert any(w.get("color") == "#FF3B30" for w in props["words"])
    assert (pub / "public" / props["audioFile"]).exists()
    clip = util.read_json(job / "clips.json")[0]
    assert (job / "clips" / clip["id"] / "final.mp4").exists()
    assert util.read_json(job / "job.json")["status"] == "done"
    assert util.read_json(job / "plan.json")["style"] == "cartoon"


def test_split_panels_and_empty_cast(tmp_path):
    from PIL import Image, ImageDraw
    from clipsuite import cartoon, characters

    img = Image.new("RGB", (600, 400), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 294, 194), fill=(90, 40, 120))     # top-left
    d.rectangle((0, 201, 294, 399), fill=(40, 90, 60))    # bottom-left
    d.rectangle((301, 0, 599, 399), fill=(120, 60, 40))   # right, full height
    src = tmp_path / "collage.png"
    img.save(src)
    boxes = [box for _, box in characters.split_panels(src, tmp_path / "out")]
    assert boxes == [(0, 0, 295, 195), (0, 201, 295, 400), (301, 0, 600, 400)]
    assert cartoon.parse_cast("none") == []


def test_cut_out_clears_specks_at_the_edge_and_white_halo(tmp_path):
    from PIL import Image, ImageDraw
    from clipsuite import characters

    img = Image.new("RGB", (400, 600), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((100, 60, 300, 260), fill=(60, 40, 30))        # head (dark hair)
    d.rectangle((195, 62, 205, 72), fill="white")            # small speck between strands, at the edge
    d.rectangle((170, 150, 180, 160), fill="white")          # eye-white deep inside: keep
    d.ellipse((98, 58, 302, 262), outline=(200, 200, 200))   # light anti-aliased ring
    src = tmp_path / "head.png"
    img.save(src)
    out = characters.cut_out(src)
    a = out.getchannel("A")
    ox, oy = 98 - 4, 58 - 4
    assert a.getpixel((200 - ox, 67 - oy)) == 0      # edge speck cleared
    assert a.getpixel((175 - ox, 155 - oy)) == 255   # inner white kept
    assert a.getpixel((98 - ox, 160 - oy)) < 128     # light halo faded


def test_split_handles_borders_small_images_and_single_pictures(tmp_path):
    from PIL import Image, ImageDraw, ImageOps
    from clipsuite import characters

    img = Image.new("RGB", (600, 400), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 294, 194), fill=(20, 15, 25))      # dark art, like a night bedroom
    d.rectangle((0, 201, 294, 399), fill=(25, 25, 25))     # 6px white gutters, like a real collage
    d.rectangle((301, 0, 599, 399), fill=(60, 30, 30))
    framed = ImageOps.expand(img, border=30, fill=(30, 30, 34)).resize((330, 230))  # screenshot, shrunk
    framed.save(tmp_path / "framed.jpg", quality=70)
    assert len(characters.split_panels(tmp_path / "framed.jpg", tmp_path / "a")) == 3
    Image.new("RGB", (500, 300), (15, 10, 20)).save(tmp_path / "dark.png")          # one dark picture
    assert len(characters.split_panels(tmp_path / "dark.png", tmp_path / "b")) == 1


def test_character_add_refuses_screenshots_of_scenes(tmp_path):
    from PIL import Image, ImageDraw
    from clipsuite import characters

    scene = Image.new("RGB", (400, 600))
    d = ImageDraw.Draw(scene)
    for y in range(600):  # gradient wall + floor, like a rendered frame
        d.line((0, y, 399, y), fill=(18 + y // 20, 12 + y // 30, 34 + y // 15))
    d.rectangle((150, 200, 250, 600), fill=(220, 200, 180))
    scene.save(tmp_path / "frame.png")
    with pytest.raises(characters.NotPlainBackground):
        characters.cut_out(tmp_path / "frame.png")
    # real art: white background, figure touching the bottom edge, slight JPEG noise
    art = Image.new("RGB", (400, 600), (252, 252, 250))
    ImageDraw.Draw(art).rectangle((120, 100, 280, 599), fill=(40, 40, 50))
    art.save(tmp_path / "art.jpg", quality=80)
    assert characters.cut_out(tmp_path / "art.jpg").size[1] > 400


def test_pronunciations_and_chatterbox_batch(ws, tmp_path, monkeypatch):
    import stat
    from clipsuite import util, voice

    monkeypatch.setattr(util, "CONFIG_FILE", tmp_path / "cfg.json")
    voice.set_pronunciation("Saito", "Sigh-toh")
    assert voice.apply_pronunciations("Meet Saito. SAITO wins.") == "Meet Sigh-toh. Sigh-toh wins."

    # fake Chatterbox environment: writes a tone per job, logs what it was asked to say
    log = tmp_path / "said.json"
    fake = tmp_path / "fakepy"
    fake.write_text(f"""#!/usr/bin/env python3
import json, subprocess, sys
jobs = json.load(open(sys.argv[2]))
json.dump(jobs, open({str(log)!r}, "w"))
for j in jobs:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=1", "-ar", "24000", j["out"]],
                   check=True, capture_output=True)
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(voice, "CHATTERBOX_PY", fake)
    sample = tmp_path / "me.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=3", str(sample)], check=True, capture_output=True)
    voice.add_voice("narrator", sample)

    work = tmp_path / "work"
    work.mkdir()
    lines = [{"text": "Meet Saito.", "voice": "narrator", "emotion": None},
             {"text": "Ruin me.", "voice": "nobody", "emotion": "1.2"}]
    wavs = voice.voice_lines(lines, work)
    said = json.loads(log.read_text())
    assert said[0]["text"] == "Meet Sigh-toh." and said[0]["voice"].endswith("narrator.wav")
    assert said[1]["voice"] == "" and said[1]["exaggeration"] == 1.2 and said[1]["cfg_weight"] == 0.35
    assert all(util.probe(w)["duration"] > 1.0 for w in wavs)
    log.unlink()
    voice.voice_lines(lines, work)          # unchanged lines are reused, nothing re-voiced
    assert not log.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_review_flow_previews_then_renders_only_kept(ws, tmp_path):
    from clipsuite import download, highlights, render, review, util

    importlib.reload(review)
    src = tmp_path / "talk.mp4"
    dur = len(SENTENCES) * 4
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=duration={dur}", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True, capture_output=True)
    job = download.import_file(src)
    util.write_json(job / "transcript.json", make_transcript())
    clips = highlights.pick(job, picker="heuristic", count=10, min_len=4, max_len=8)
    assert len(clips) >= 3

    render.preview_all(job, defaults={"reframe": "crop"})
    clips = util.read_json(job / "clips.json")
    for c in clips:
        p = job / "clips" / c["id"] / "preview.mp4"
        assert p.exists() and util.probe(p)["height"] == 960 and c["decision"] == "pending"
        assert not (job / "clips" / c["id"] / "final.mp4").exists()

    review.decide(job, ["1", "3"], "keep")
    review.decide(job, ["2"], "skip")
    with pytest.raises(ValueError):
        review.decide(job, ["99"], "keep")
    assert "[KEEP]" in review.summary(job)[0] and "[skip]" in review.summary(job)[1]

    ready = review.finish(job, {"reframe": "crop"})
    clips = util.read_json(job / "clips.json")
    rendered = [c["id"] for c in clips if (job / "clips" / c["id"] / "final.mp4").exists()]
    assert rendered == [clips[0]["id"], clips[2]["id"]]
    files = sorted(p.name for p in ready.glob("*.mp4"))
    assert len(files) == 2 and files[0].startswith("01-") and files[1].startswith("02-")
    assert util.probe(ready / files[0])["height"] == 1920
    assert "Caption idea" in (ready / "POSTING.txt").read_text()
    assert util.read_json(job / "job.json")["status"] == "done"
