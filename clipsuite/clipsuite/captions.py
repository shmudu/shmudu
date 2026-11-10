"""Word-by-word "karaoke" captions as .ass (burned in by FFmpeg) and .srt (for editors)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import fmt_ts

# Colors are &HBBGGRR (ASS is blue-green-red).
PRESETS: dict[str, dict[str, Any]] = {
    "bold": {"font": "Montserrat Black", "size": 92, "color": "&H00FFFFFF", "highlight": "&H0000E5FF",
             "outline": 7, "shadow": 2, "box": False, "uppercase": True, "words_per_line": 3, "pop": True},
    "clean": {"font": "Inter", "size": 72, "color": "&H00FFFFFF", "highlight": "&H00FFC94A",
              "outline": 4, "shadow": 0, "box": False, "uppercase": False, "words_per_line": 4, "pop": False},
    "boxed": {"font": "Arial Black", "size": 76, "color": "&H00FFFFFF", "highlight": "&H0055FF55",
              "outline": 0, "shadow": 0, "box": True, "uppercase": False, "words_per_line": 4, "pop": False},
    "minimal": {"font": "Helvetica", "size": 60, "color": "&H00FFFFFF", "highlight": "&H00FFFFFF",
                "outline": 3, "shadow": 1, "box": False, "uppercase": False, "words_per_line": 6, "pop": False},
}


def style_for(overrides: dict[str, Any] | None) -> dict[str, Any]:
    overrides = overrides or {}
    base = dict(PRESETS.get(overrides.get("preset", "bold"), PRESETS["bold"]))
    base.update({k: v for k, v in overrides.items() if k in base})
    if "position" in overrides:
        base["position"] = overrides["position"]
    return base


def clip_words(words: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    """Words inside [start, end], re-timed so the clip starts at 0."""
    out = []
    for w in words:
        if w["end"] <= start or w["start"] >= end:
            continue
        out.append({"w": w["w"], "start": round(max(w["start"], start) - start, 3),
                    "end": round(min(w["end"], end) - start, 3)})
    return out


def chunk(words: list[dict[str, Any]], per_line: int, max_gap: float = 0.6) -> list[list[dict[str, Any]]]:
    """Group words into short caption lines, breaking on pauses and sentence ends."""
    groups: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for w in words:
        if cur and (len(cur) >= per_line or w["start"] - cur[-1]["end"] > max_gap
                    or cur[-1]["w"].endswith((".", "?", "!"))):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words: list[dict[str, Any]], width: int = 1080, height: int = 1920,
              style: dict[str, Any] | None = None, title: str = "", title_secs: float = 3.0) -> str:
    st = style_for(style)
    pos = st.get("position", 0.70)  # fraction of frame height for the caption baseline
    margin_v = int(height * (1 - pos))
    border_style = 3 if st["box"] else 1
    back = "&H99000000" if st["box"] else "&H80000000"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{st['size']},{st['color']},{st['highlight']},&H00000000,{back},1,0,0,0,100,100,0,0,{border_style},{st['outline'] if not st['box'] else 18},{st['shadow']},2,60,60,{margin_v},1
Style: Title,{st['font']},{int(st['size'] * 0.8)},&H00FFFFFF,&H00FFFFFF,&H00000000,&HCC000000,1,0,0,0,100,100,0,0,3,20,0,8,80,80,{int(height * 0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if title:
        events.append(f"Dialogue: 1,{_ass_ts(0)},{_ass_ts(title_secs)},Title,,0,0,0,,"
                      f"{{\\fad(150,250)}}{_esc(title)}")
    for group in chunk(words, st["words_per_line"]):
        for k, active in enumerate(group):
            t0 = active["start"]
            t1 = group[k + 1]["start"] if k + 1 < len(group) else active["end"]
            if t1 - t0 < 0.02:
                continue
            parts = []
            for m, w in enumerate(group):
                txt = _esc(w["w"].upper() if st["uppercase"] else w["w"])
                if m == k:
                    pop = r"\fscx112\fscy112" if st["pop"] else ""
                    parts.append(f"{{\\c{st['highlight']}{pop}}}{txt}{{\\c{st['color']}\\fscx100\\fscy100}}")
                else:
                    parts.append(txt)
            events.append(f"Dialogue: 0,{_ass_ts(t0)},{_ass_ts(t1)},Cap,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(events) + "\n"


def _ass_ts(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_srt(words: list[dict[str, Any]], per_line: int = 6) -> str:
    out = []
    for i, g in enumerate(chunk(words, per_line), 1):
        out += [str(i), f"{fmt_ts(g[0]['start'])} --> {fmt_ts(g[-1]['end'])}", " ".join(w["w"] for w in g), ""]
    return "\n".join(out)


def write(words: list[dict[str, Any]], out_dir: Path, style: dict[str, Any] | None = None,
          width: int = 1080, height: int = 1920, title: str = "") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ass, srt = out_dir / "captions.ass", out_dir / "captions.srt"
    ass.write_text(build_ass(words, width, height, style, title=title))
    srt.write_text(build_srt(words))
    return ass, srt


def _hex_to_ass(color: str) -> str:
    c = color.lstrip("#")
    return f"&H00{c[4:6]}{c[2:4]}{c[0:2]}".upper() if len(c) == 6 else "&H0000E5FF"


def build_headline_ass(headline: str, dur: float, width: int = 1080, height: int = 1920,
                       accent: str = "#FFE500") -> str:
    """Big centred headline card with a pop-in, an accent underline and a fade-out."""
    acc = _hex_to_ass(accent)
    size = 118 if len(headline) <= 22 else 96 if len(headline) <= 40 else 80
    bar_y = int(height * 0.54)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Head,Montserrat Black,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,3,5,90,90,0,1
Style: Bar,Arial,10,{acc},{acc},{acc},{acc},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{_ass_ts(0.05)},{_ass_ts(dur)},Bar,,0,0,0,,{{\\an7\\pos({width // 2 - 150},{bar_y})\\fad(200,200)\\1c{acc}\\bord0\\shad0\\p1}}m 0 0 l 300 0 300 16 0 16{{\\p0}}
Dialogue: 1,{_ass_ts(0.1)},{_ass_ts(dur)},Head,,0,0,0,,{{\\an5\\pos({width // 2},{int(height * 0.44)})\\fad(150,200)\\fscx80\\fscy80\\t(0,280,\\fscx100\\fscy100)}}{_esc(headline)}
"""
