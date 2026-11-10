"""clipsuite command line.

  clipsuite auto <url-or-file>           everything: download, transcribe, pick, render, exports
  clipsuite create --script my-script.txt make a faceless video from your own script
  clipsuite serve                         phone-friendly web editor on your Wi-Fi
  clipsuite doctor                        check which tools are installed
Run `clipsuite <command> -h` for details.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path

from .util import WORKSPACE, ToolMissing, ffmpeg_has_filter, get_setting, job_dir, list_jobs, read_json


def _job(name: str) -> Path:
    if name == "latest":
        jobs = list_jobs()
        if not jobs:
            sys.exit("No jobs yet.")
        name = jobs[0]["id"]
    d = job_dir(name)
    if not d.exists():
        sys.exit(f"No job named {name!r} in {WORKSPACE}")
    return d


def _stock_ok() -> bool:
    from .create import has_stock_source
    return has_stock_source()


def _tts() -> list[str]:
    from .create import tts_backends
    return tts_backends()


def _opencv_ok() -> bool:
    """True only if OpenCV imports AND has face detection (half-installed copies don't)."""
    if not importlib.util.find_spec("cv2"):
        return False
    try:
        import cv2  # type: ignore
        return not cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").empty()
    except Exception:
        return False


def cmd_doctor(_a: argparse.Namespace) -> None:
    from .transcribe import available_backends

    rows = [
        ("ffmpeg", bool(shutil.which("ffmpeg")), "brew install homebrew-ffmpeg/ffmpeg/ffmpeg"),
        ("ffmpeg captions (libass)", ffmpeg_has_filter("ass"),
         "brew uninstall --ignore-dependencies ffmpeg && brew tap homebrew-ffmpeg/ffmpeg && "
         "brew install homebrew-ffmpeg/ffmpeg/ffmpeg"),
        ("yt-dlp", bool(shutil.which("yt-dlp")), "brew install yt-dlp"),
        ("whisper backend", bool(available_backends()), "pip install mlx-whisper  (Apple Silicon)"),
        ("node/npx (Remotion, HyperFrames)", bool(shutil.which("npx")), "brew install node"),
        ("anthropic SDK (Claude clip picker)", bool(importlib.util.find_spec("anthropic")), "pip install anthropic"),
        ("voice for `create` (Kokoro / say)", bool(_tts()), "pip install 'kokoro>=0.9.4' soundfile"),
        ("stock footage for `create`", _stock_ok(),
         "clipsuite config footage_dir ~/Movies/Broll  and/or  clipsuite config pixabay_api_key KEY "
         "(free key: pixabay.com/api/docs)"),
        ("opencv (face-tracked crop)", _opencv_ok(),
         "pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python && "
         "pip install --force-reinstall opencv-python-headless"),
        ("DaVinci Resolve", Path("/Applications/DaVinci Resolve/DaVinci Resolve.app").exists(),
         "download from blackmagicdesign.com/products/davinciresolve"),
    ]
    for name, ok, fix in rows:
        print(f"  {'OK ' if ok else '-- '} {name:40s} {'' if ok else '-> ' + fix}")
    print(f"\n  whisper backends found: {', '.join(available_backends()) or 'none'}")
    print(f"  workspace: {WORKSPACE}")


def cmd_auto(a: argparse.Namespace) -> None:
    from . import pipeline

    job = pipeline.ingest(a.source)
    print(f"Job: {job.name}")
    pipeline.process(job, vars(a) | {"style": {"preset": a.preset, "reframe": a.reframe}})
    _summary(job)


def cmd_download(a: argparse.Namespace) -> None:
    from . import pipeline
    print(pipeline.ingest(a.source).name)


def cmd_transcribe(a: argparse.Namespace) -> None:
    from . import transcribe
    t = transcribe.transcribe(_job(a.job), a.backend, a.model, a.language, force=a.force)
    print(f"{len(t['segments'])} segments ({t.get('backend')}, {t.get('language')})")


def cmd_pick(a: argparse.Namespace) -> None:
    from . import highlights
    for c in highlights.pick(_job(a.job), a.picker, a.count, a.min_len, a.max_len, a.guidance):
        print(f"  {c['id']:40s} {c['start']:8.1f}-{c['end']:8.1f}  score {c['score']}  {c['reason']}")


def cmd_render(a: argparse.Namespace) -> None:
    from . import render
    render.render_all(_job(a.job), a.only, {"preset": a.preset, "reframe": a.reframe})
    _summary(_job(a.job))


def cmd_remotion(a: argparse.Namespace) -> None:
    from . import remotion
    print(remotion.render(_job(a.job), a.clip, preview=a.studio))


def cmd_hyperframes(a: argparse.Namespace) -> None:
    from . import hyperframes
    print(hyperframes.build(_job(a.job), a.clip, cta=a.cta, render=not a.no_render))


def cmd_resolve(a: argparse.Namespace) -> None:
    from . import resolve
    if a.push:
        print("Imported into Resolve project:", resolve.push_to_resolve(_job(a.job)))
    else:
        print(resolve.export_fcpxml(_job(a.job)), "\n-> In Resolve: File > Import > Timeline...")


def cmd_chatcut(a: argparse.Namespace) -> None:
    from . import chatcut
    print(chatcut.export(_job(a.job)), "\n-> Upload a clip's raw.mp4 to ChatCut and paste its BRIEF.md")


def cmd_broll(a: argparse.Namespace) -> None:
    from . import wan2gp
    if a.action == "prompts":
        print(wan2gp.write_prompts(_job(a.job)))
    else:
        c = wan2gp.attach(_job(a.job), a.clip, [Path(f) for f in a.files], a.at, a.duration)
        print(f"{len(c['broll'])} b-roll inserts on {c['id']}. Re-render: clipsuite render {a.job} --only {a.clip}")


def cmd_create(a: argparse.Namespace) -> None:
    from . import create
    from .util import get_setting

    cartoon = a.style == "cartoon"
    kw = {"tts": a.tts, "music": a.music, "preset": a.preset, "footage_dir": a.footage or ""}
    if a.rebuild:
        create.rebuild(_job(a.rebuild), voice=a.voice, **kw)
        return
    if a.script:
        script = Path(a.script).expanduser()
        if not script.exists() and (WORKSPACE / "_drafts" / script.name).exists():
            script = WORKSPACE / "_drafts" / script.name  # allow just the draft's file name
        if not script.exists():
            topic = a.topic or script.stem.replace("-", " ").replace("_", " ")
            if cartoon:
                from . import cartoon as cartoon_mod
                cartoon_mod.write_template(topic, script)
            else:
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text(create.TEMPLATE.format(title=topic, query=create.keywords(topic)))
            style = " --style cartoon" if cartoon else ""
            sys.exit(f"That script didn't exist, so I made a template there:\n  {script.resolve()}\n\n"
                     f"Fill it in, save, then run the same command again:\n  open -e '{script}'\n"
                     f"  clipsuite create{style} --script '{script}'")
        plan = create.parse_script(script.read_text(), default_title=a.topic or "")
        if "Write your hook here" in plan["scenes"][0]["text"]:
            sys.exit(f"{script} still has the template text. Replace it with your own script first:\n"
                     f"  open -e '{script}'")
    elif a.topic and cartoon:
        from . import cartoon as cartoon_mod
        draft = cartoon_mod.write_template(a.topic)
        print(f"Cartoon script template (an example episode you can edit):\n\n  open -e '{draft}'"
              f"\n  clipsuite create --style cartoon --script '{draft}'")
        return
    elif a.topic and (get_setting("anthropic_api_key") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("Claude is writing the script...", flush=True)
        plan = create.plan_with_claude(a.topic, a.seconds, a.tone)
    elif a.topic:
        draft = create.write_template(a.topic)
        print(f"Free mode: write your script in this file, then run the command it shows.\n\n  open -e '{draft}'"
              f"\n  clipsuite create --script '{draft}'\n\n(Or set ANTHROPIC_API_KEY to have Claude write it.)")
        return
    else:
        sys.exit("Give a topic, --script FILE, or --rebuild JOB")
    if cartoon:
        from . import cartoon as cartoon_mod
        cartoon_mod.build(plan, voice=a.voice, tts=a.tts, music=a.music)
    else:
        create.build(plan, voice=a.voice, **kw)


def cmd_character(a: argparse.Namespace) -> None:
    from . import characters

    if a.action == "list":
        found = characters.list_all()
        print("Characters: " + (", ".join(found["characters"]) or "(none yet)"))
        print("Backgrounds: " + (", ".join(found["backgrounds"]) or "(none added)") +
              "   built in: bedroom, gym, plain")
        return
    if not a.name or not a.image:
        sys.exit("Usage: clipsuite character add NAME IMAGE [--part left|right] [--keep-background]")
    if a.kind == "background":
        print("Saved", characters.add_background(a.name, Path(a.image)))
    else:
        out = characters.add_character(a.name, Path(a.image), a.part, a.keep_background)
        print(f"Saved {out}\nUse it in a script with:  > show: {a.name}")


def cmd_config(a: argparse.Namespace) -> None:
    from .util import CONFIG_FILE, set_setting

    if a.value is None:
        print(f"{a.name} = {'(set)' if get_setting(a.name) else '(not set)'}   [{CONFIG_FILE}]")
        return
    value = a.value
    if a.name == "footage_dir":
        folder = Path(value).expanduser().resolve()
        if not folder.is_dir():
            sys.exit(f"No such folder: {folder}")
        value = str(folder)
    print("Saved to", set_setting(a.name, value))


def cmd_serve(a: argparse.Namespace) -> None:
    from . import server
    server.serve(a.host, a.port, open_access=a.no_token)


def cmd_list(_a: argparse.Namespace) -> None:
    for j in list_jobs():
        print(f"  {j['id']:50s} {j.get('status', '?'):12s} {j.get('title', '')}")


def _summary(job: Path) -> None:
    print("\nRendered shorts:")
    for c in read_json(job / "clips.json", []):
        f = job / "clips" / c["id"] / "final.mp4"
        if f.exists():
            print(f"  {f}")
    print(f"\nExports: {job / 'exports'}")


def _pick_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--picker", choices=["auto", "heuristic", "claude"], default="auto")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--min-len", type=float, default=20)
    p.add_argument("--max-len", type=float, default=60)
    p.add_argument("--guidance", default="", help="e.g. 'funny moments only' or 'actionable tips'")


def _style_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--preset", choices=["bold", "clean", "boxed", "minimal"], default="bold")
    p.add_argument("--reframe", choices=["auto", "face", "crop", "blur", "fit"], default="auto")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="clipsuite", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check installed tools").set_defaults(fn=cmd_doctor)
    sub.add_parser("list", help="list jobs").set_defaults(fn=cmd_list)

    p = sub.add_parser("auto", help="full pipeline from a URL or file")
    p.add_argument("source")
    p.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster", "openai"])
    p.add_argument("--model")
    p.add_argument("--language")
    _pick_args(p)
    _style_args(p)
    p.set_defaults(fn=cmd_auto)

    p = sub.add_parser("download", help="yt-dlp a URL (or import a local file) into a new job")
    p.add_argument("source")
    p.set_defaults(fn=cmd_download)

    p = sub.add_parser("transcribe", help="Whisper transcript with word timings")
    p.add_argument("job")
    p.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster", "openai"])
    p.add_argument("--model")
    p.add_argument("--language")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_transcribe)

    p = sub.add_parser("pick", help="choose highlight clips")
    p.add_argument("job")
    _pick_args(p)
    p.set_defaults(fn=cmd_pick)

    p = sub.add_parser("render", help="FFmpeg: cut, reframe, caption")
    p.add_argument("job")
    p.add_argument("--only", nargs="*")
    _style_args(p)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("remotion", help="render a clip with the Remotion caption template")
    p.add_argument("job")
    p.add_argument("clip")
    p.add_argument("--studio", action="store_true", help="open Remotion Studio to tweak visually")
    p.set_defaults(fn=cmd_remotion)

    p = sub.add_parser("hyperframes", help="add HyperFrames intro/outro cards to a clip")
    p.add_argument("job")
    p.add_argument("clip")
    p.add_argument("--cta", default="Follow for part 2")
    p.add_argument("--no-render", action="store_true", help="only write the editable HTML")
    p.set_defaults(fn=cmd_hyperframes)

    p = sub.add_parser("resolve", help="export FCPXML for DaVinci Resolve (or --push into a running Resolve)")
    p.add_argument("job")
    p.add_argument("--push", action="store_true")
    p.set_defaults(fn=cmd_resolve)

    p = sub.add_parser("chatcut", help="build ChatCut upload bundles + edit briefs")
    p.add_argument("job")
    p.set_defaults(fn=cmd_chatcut)

    p = sub.add_parser("broll", help="Wan2GP b-roll: write prompts, or attach generated videos")
    p.add_argument("action", choices=["prompts", "attach"])
    p.add_argument("job")
    p.add_argument("clip", nargs="?")
    p.add_argument("files", nargs="*")
    p.add_argument("--at", type=float, nargs="*", help="seconds into the clip for each file")
    p.add_argument("--duration", type=float, default=2.5)
    p.set_defaults(fn=cmd_broll)

    p = sub.add_parser("create", help="make a faceless video from a script (free) or a topic (Claude)")
    p.add_argument("topic", nargs="?", help="what the video is about (Claude writes it if you have a key)")
    p.add_argument("--script", help="text file with your script (see `clipsuite create -h` docs in README)")
    p.add_argument("--rebuild", metavar="JOB", help="rebuild a created job after editing its plan.json")
    p.add_argument("--voice", default="", help="Kokoro voice, e.g. af_heart, am_michael, bf_emma (or a macOS voice)")
    p.add_argument("--tts", default="auto", choices=["auto", "kokoro", "say", "espeak"])
    p.add_argument("--music", help="background music file (auto-ducked under the voice)")
    p.add_argument("--footage", help="folder of your own b-roll clips to use (matched by file/folder names)")
    p.add_argument("--seconds", type=int, default=75, help="target length when Claude writes the script")
    p.add_argument("--style", choices=["stock", "cartoon"], default="stock",
                   help="stock: footage + headline cards; cartoon: your characters, story series look")
    p.add_argument("--tone", default="", help="tone notes for Claude, e.g. 'calm, educational'")
    p.add_argument("--preset", choices=["bold", "clean", "boxed", "minimal"], default="bold")
    p.set_defaults(fn=cmd_create)

    for kind in ("character", "background"):
        p = sub.add_parser(kind, help=f"add your own {kind} art for `create --style cartoon`, or list them")
        p.add_argument("action", choices=["add", "list"])
        p.add_argument("name", nargs="?")
        p.add_argument("image", nargs="?")
        p.add_argument("--part", choices=["full", "left", "right"], default="full",
                       help="take only the left or right half of the image (for side-by-side art)")
        p.add_argument("--keep-background", action="store_true", help="don't cut the character out")
        p.set_defaults(fn=cmd_character, kind=kind)

    p = sub.add_parser("config", help="save a setting, e.g. `clipsuite config pixabay_api_key KEY`")
    p.add_argument("name", choices=["pixabay_api_key", "footage_dir", "pexels_api_key"])
    p.add_argument("value", nargs="?")
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("serve", help="web editor you can open from your phone")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-token", action="store_true", help="disable the access token (trusted networks only)")
    p.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    if a.cmd == "broll" and a.action == "attach" and (not a.clip or not a.files):
        ap.error("broll attach needs: <job> <clip-id> <file> [file...]")
    try:
        a.fn(a)
    except ToolMissing as e:
        sys.exit(f"Missing tool: {e}\nRun `clipsuite doctor` for the full checklist.")


if __name__ == "__main__":
    main()
