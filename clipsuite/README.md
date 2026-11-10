# ClipSuite ✂️

Turn long videos (podcasts, streams, YouTube) into captioned vertical shorts, then edit
them on your phone or hand them to a real editor.

```
 link / file ─► yt-dlp ─► Whisper ─► pick highlights ─► FFmpeg render ─► final.mp4 (9:16, captions)
                                     (heuristic or      (cut, reframe,      │
                                      Claude API)        loudness, b-roll)  ├─► Remotion   animated-caption template
                                                                            ├─► HyperFrames intro/outro motion cards
                                                                            ├─► DaVinci Resolve  FCPXML timelines + SRT
                                                                            ├─► ChatCut    upload bundle + edit brief
                                                                            └─► Wan2GP     AI b-roll prompts → inserts
```

| Tool | What it does here |
|---|---|
| **yt-dlp** | Downloads the source video (YouTube, TikTok, Twitch VODs, podcasts…). |
| **Whisper** | Transcribes with word-level timestamps. `mlx-whisper` on Apple Silicon, `faster-whisper` elsewhere. |
| **FFmpeg** | Cuts clips, reframes to 1080×1920 (face-tracked crop, center crop, blurred background or letterbox), normalizes loudness to −14 LUFS, overlays b-roll, burns word-by-word captions. |
| **Remotion** | React template (`remotion/`) with spring-animated captions, a hook title and a progress bar. Open in Remotion Studio to tweak visually. |
| **HyperFrames** | HeyGen's open-source HTML→video renderer. Builds an intro hook card and an outro CTA card (plain HTML + GSAP you can edit) and stitches them around the clip. |
| **DaVinci Resolve** | FCPXML with a "Selects" timeline (all clips from the 16:9 source, for re-trimming) plus one vertical timeline per clip; captions as `.srt`. Can also push straight into a running Resolve. |
| **ChatCut** | Per-clip bundle (clean cut, captions, transcript) plus a written `BRIEF.md` to paste into ChatCut's chat for an AI polish pass. |
| **Wan2GP** | Writes b-roll prompts per clip (Claude writes them when it picks clips); you generate in Wan2GP, then `clipsuite broll attach` composites the results. |

## Install on your Mac

```bash
git clone <this repo> && cd shmudu/clipsuite
bash setup/install_mac.sh
source .venv/bin/activate
clipsuite doctor
```

The script installs Homebrew (if missing), FFmpeg with caption support (from the `homebrew-ffmpeg` tap, since Homebrew's standard `ffmpeg` no longer includes libass), `yt-dlp`, `node`, Python 3.12, `mlx-whisper`,
`anthropic`, OpenCV (for face tracking) and the Remotion packages, and runs `hyperframes doctor`.

Install these apps yourself:

- **DaVinci Resolve** (free): https://www.blackmagicdesign.com/products/davinciresolve
- **ChatCut**: https://chatcut.io (web or desktop app)
- **Wan2GP**: built for NVIDIA GPUs. Apple Silicon support is experimental, through the
  [Pinokio](https://pinokio.co) launcher, and slow. For real use, run it on a PC with an NVIDIA
  card or a rented cloud GPU (`git clone https://github.com/deepbeepmeep/Wan2GP`, then follow its README).
- *Optional:* a Claude API key (`export ANTHROPIC_API_KEY=...`) so Claude picks and titles clips
  and writes b-roll prompts. Without one, a free offline heuristic picks the clips.

The first transcription downloads the Whisper model (~1.5 GB).

## Use it

### From your phone

```bash
clipsuite serve
```

It prints a link like `http://192.168.1.20:8765/?t=abc123`. Open it on your phone on the same
Wi-Fi. From there you can paste a link or upload a video from your camera roll, then:

- watch each short as it renders and download it (with or without captions)
- change in/out points (±1s nudges), the title, caption style, framing and caption height, then re-render
- add a clip by timestamp, or remove one
- export the DaVinci, ChatCut and Wan2GP bundles

Keep the Mac awake while it works (`caffeinate -i clipsuite serve`).

### From the terminal

```bash
clipsuite auto "https://www.youtube.com/watch?v=..." --count 5 --max-len 60 --preset bold
clipsuite auto ~/Movies/podcast.mov --guidance "actionable money tips only"

# or step by step (use `latest` for the newest job)
clipsuite download URL
clipsuite transcribe latest
clipsuite pick latest --picker claude --count 8
nano workspace/<job>/clips.json          # tweak start/end/title/style by hand if you like
clipsuite render latest --reframe face --preset clean

clipsuite remotion latest 01-my-clip [--studio]   # Remotion version -> remotion.mp4
clipsuite hyperframes latest 01-my-clip --cta "Full episode on YouTube"
clipsuite resolve latest [--push]
clipsuite chatcut latest
clipsuite broll prompts latest
clipsuite broll attach latest 01-my-clip ~/Downloads/wan_001.mp4 ~/Downloads/wan_002.mp4
clipsuite render latest --only 01-my-clip          # re-render with b-roll
```

Output lives in `workspace/<job>/`:

```
source.mp4  transcript.json/.srt  clips.json  job.json
clips/<id>/raw.mp4 final.mp4 captions.ass captions.srt words.json thumb.jpg
exports/resolve.fcpxml  exports/chatcut.zip  exports/wan2gp/prompts.txt
```

### Per-clip style options (`clips.json` → `"style"`)

| key | values |
|---|---|
| `preset` | `bold` (yellow highlight), `clean`, `boxed`, `minimal` |
| `reframe` | `auto`, `face`, `crop`, `blur`, `fit` |
| `crop_x` | 0–1 horizontal crop centre (for `crop`) |
| `position` | 0.4–0.9 caption height |
| `words_per_line`, `uppercase`, `font`, `size` | caption overrides |
| `show_title`, `captions` | `true`/`false` |

## Editing in DaVinci Resolve

1. `clipsuite resolve latest`
2. In Resolve, go to **File → Import → Timeline…** and pick `workspace/<job>/exports/resolve.fcpxml`.
3. You get a **Selects** timeline (the original 16:9 cuts; use Smart Reframe or re-trim here) and
   a **Short …** timeline per clip at 1080×1920. Drag `clips/<id>/captions.srt` onto a subtitle
   track to get editable captions.

To have ClipSuite do the import, open Resolve, set **Preferences → System → General → External
scripting using: Local**, then run `clipsuite resolve latest --push`. If your Resolve version
doesn't allow external scripting, use the manual import above.

## ChatCut

`clipsuite chatcut latest` makes `exports/chatcut/<clip>/` folders. Each has `raw.mp4`,
`captions.srt`, `transcript.txt` and `BRIEF.md`. Upload `raw.mp4` to ChatCut and paste the brief
into its chat. ChatCut also has a Claude Code plugin if you prefer to drive it from Claude Code.

## Wan2GP b-roll

1. `clipsuite broll prompts latest` writes `exports/wan2gp/<clip>.txt` (one prompt per line, portrait framing).
2. In Wan2GP, pick a Wan 2.x text-to-video model at 480×832, paste the prompts, and generate.
3. `clipsuite broll attach latest <clip-id> clip1.mp4 clip2.mp4 [--at 6 14] [--duration 2.5]`.
   Without `--at`, the inserts are spread through the clip and kept off the opening hook.
4. Re-render the clip.

## Tests

```bash
pip install -e '.[dev]' && pytest -q
```

The tests build a synthetic video and run the real FFmpeg pipeline (render, b-roll, FCPXML,
ChatCut bundle, HyperFrames stitching). They don't need Whisper or network access.
