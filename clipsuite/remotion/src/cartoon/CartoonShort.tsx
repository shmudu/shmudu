import "@fontsource/anton";
import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BUILT_IN } from "./Backgrounds";

const W = 1080;
const H = 1920;
const FLOOR_Y = 0.92; // where characters' feet touch, as a fraction of height
const FONT = "Anton, Impact, 'Arial Narrow', sans-serif";

export type CastMember = {
  sprite: string; // path inside remotion/public, or "" for a placeholder silhouette
  name: string;
  x: number; // 0..1 horizontal centre
  height: number; // fraction of frame height
  flip?: boolean;
  closeup?: boolean; // mid-shot: bottom edge sits below the frame (for art cut off at the legs)
  anim?: string[]; // idle (always) + bounce | shake | enter | glow
};
export type HudItem = { label: string; value: string; color?: string };
export type VoteSide = { title: string; sub: string };
export type Scene = {
  start: number;
  end: number;
  background: string; // built-in name ("bedroom", "gym", "plain") or an image path in public/
  cast: CastMember[];
  hud?: HudItem[];
  banner?: string;
  note?: string;
  vote?: { a: VoteSide; b: VoteSide };
};
export type CWord = { w: string; start: number; end: number; color?: string };
export type CartoonProps = {
  audioFile: string;
  durationInSeconds: number;
  scenes: Scene[];
  words: CWord[];
  wordsPerLine: number;
  captionPosition: number;
};

// ---------------------------------------------------------------- helpers

const useFontReady = () => {
  const [handle] = useState(() => delayRender("Loading Anton font"));
  useEffect(() => {
    document.fonts
      .load(`120px Anton`)
      .then(() => continueRender(handle))
      .catch(() => continueRender(handle));
  }, [handle]);
};

const toLines = (words: CWord[], perLine: number): CWord[][] => {
  const lines: CWord[][] = [];
  let cur: CWord[] = [];
  for (const w of words) {
    const prev = cur[cur.length - 1];
    if (prev && (cur.length >= perLine || w.start - prev.end > 0.45 || /[.?!,]$/.test(prev.w))) {
      lines.push(cur);
      cur = [];
    }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  return lines;
};

// ---------------------------------------------------------------- pieces

const Background: React.FC<{ name: string; sceneStart: number; sceneEnd: number }> = ({ name, sceneStart, sceneEnd }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const Builtin = BUILT_IN[name];
  if (Builtin) return <Builtin />;
  if (name) {
    // slow pan + push-in, so wide art shows more of the room and stills feel cinematic
    const p = interpolate(frame / fps, [sceneStart, Math.max(sceneStart + 0.1, sceneEnd)], [0, 1], {
      extrapolateLeft: "clamp", extrapolateRight: "clamp" });
    const dir = Math.round(sceneStart * 10) % 2 === 0 ? 1 : -1;
    return (
      <Img src={staticFile(name)} style={{ position: "absolute", inset: 0, width: W, height: H, objectFit: "cover",
        objectPosition: `${50 + dir * interpolate(p, [0, 1], [-18, 18])}% 50%`,
        transform: `scale(${interpolate(p, [0, 1], [1.02, 1.1])})` }} />
    );
  }
  return <BUILT_IN.plain />;
};

const Placeholder: React.FC<{ name: string; h: number }> = ({ name, h }) => (
  <svg width={h * 0.42} height={h} viewBox="0 0 420 1000">
    <circle cx="210" cy="140" r="110" fill="#d9d2c5" stroke="#111" strokeWidth="10" />
    <rect x="70" y="270" width="280" height="380" rx="90" fill="#bdb6a8" stroke="#111" strokeWidth="10" />
    <rect x="100" y="620" width="90" height="360" rx="30" fill="#4a4f66" stroke="#111" strokeWidth="10" />
    <rect x="230" y="620" width="90" height="360" rx="30" fill="#4a4f66" stroke="#111" strokeWidth="10" />
    <text x="210" y="470" textAnchor="middle" fontFamily={FONT} fontSize="54" fill="#111">{name.toUpperCase()}</text>
  </svg>
);

const Character: React.FC<{ c: CastMember; sceneStart: number; i: number }> = ({ c, sceneStart, i }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const local = t - sceneStart;
  const anim = c.anim ?? [];
  const h = c.height * H;
  const phase = i * 1.7;

  // idle breathing / sway: every character is always a little alive
  let sy = 1 + 0.014 * Math.sin((t + phase) * 2.6);
  let rot = 1.2 * Math.sin((t + phase) * 1.3);
  let dx = 0;
  let dy = 0;
  if (anim.includes("bounce")) dy -= Math.abs(Math.sin(local * 7)) * 26;
  if (anim.includes("shake") && local < 0.8) dx += Math.sin(local * 60) * 12 * (1 - local / 0.8);
  if (anim.includes("enter")) {
    const s = spring({ frame: frame - Math.round(sceneStart * fps), fps, config: { damping: 15, stiffness: 120 } });
    dx += interpolate(s, [0, 1], [c.x < 0.5 ? -W * 0.7 : W * 0.7, 0]);
  }
  let pop = 1;
  if (anim.includes("glow")) {
    const s = spring({ frame: frame - Math.round(sceneStart * fps), fps, config: { damping: 9, stiffness: 140 } });
    pop = interpolate(s, [0, 1], [0.7, 1]);
  }
  if (anim.includes("still")) {
    sy = 1;
    rot = 0;
  }

  return (
    <div
      style={{
        position: "absolute",
        left: c.x * W,
        top: (c.closeup ? 1.03 : FLOOR_Y) * H,
        transform: `translate(-50%, -100%) translate(${dx}px, ${dy}px)`,
      }}
    >
      {/* floor shadow */}
      {c.closeup ? null : <div style={{ position: "absolute", left: "50%", bottom: -18, width: h * 0.36, height: 36, borderRadius: "50%",
        background: "rgba(0,0,0,.45)", transform: "translateX(-50%)", filter: "blur(4px)" }} />}
      <div style={{ transformOrigin: "50% 100%", transform: `scale(${pop}) scaleX(${c.flip ? -1 : 1}) scaleY(${sy}) rotate(${rot}deg)` }}>
        {c.sprite ? <Img src={staticFile(c.sprite)} style={{ height: h, width: "auto", display: "block" }} /> : <Placeholder name={c.name} h={h} />}
      </div>
    </div>
  );
};

const Hud: React.FC<{ items: HudItem[] }> = ({ items }) => (
  <div style={{ position: "absolute", top: 70, left: 40, right: 40, display: "flex", gap: 16 }}>
    {items.map((it, i) => (
      <div key={i} style={{ background: "rgba(10,10,16,.82)", borderRadius: 16, padding: "12px 26px", textAlign: "center",
        border: "3px solid rgba(255,255,255,.08)", minWidth: 150 }}>
        <div style={{ fontFamily: FONT, color: "#d9d9e3", fontSize: 30, letterSpacing: 1 }}>{it.label}</div>
        <div style={{ fontFamily: FONT, color: it.color ?? "#FFD60A", fontSize: 64, lineHeight: 1.05 }}>{it.value}</div>
      </div>
    ))}
  </div>
);

const Banner: React.FC<{ text: string; sceneStart: number }> = ({ text, sceneStart }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - Math.round(sceneStart * fps), fps, config: { damping: 13 } });
  return (
    <div style={{ position: "absolute", top: 300, left: 0, right: 0, display: "flex", justifyContent: "center",
      transform: `translateY(${interpolate(s, [0, 1], [-140, 0])}px)`, opacity: s }}>
      <div style={{ fontFamily: FONT, fontSize: 70, color: "white", background: "#121218", padding: "14px 40px",
        borderRadius: 18, border: "6px solid #FFD60A", boxShadow: "0 10px 0 rgba(0,0,0,.5)", textAlign: "center", maxWidth: 940 }}>
        {text}
      </div>
    </div>
  );
};

const Note: React.FC<{ text: string; sceneStart: number }> = ({ text, sceneStart }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - Math.round((sceneStart + 0.35) * fps), fps, config: { damping: 8, stiffness: 160 } });
  return (
    <div style={{ position: "absolute", right: 80, top: 640, width: 300, height: 280, background: "#FFE14D",
      boxShadow: "0 18px 30px rgba(0,0,0,.45)", transform: `rotate(6deg) scale(${s})`, display: "flex",
      alignItems: "center", justifyContent: "center", fontFamily: FONT, fontSize: 96, color: "#111", textAlign: "center",
      padding: 16, lineHeight: 1 }}>
      {text}
    </div>
  );
};

const VoteCard: React.FC<{ vote: { a: VoteSide; b: VoteSide }; cast: CastMember[]; sceneStart: number }> = ({ vote, cast, sceneStart }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - Math.round(sceneStart * fps), fps, config: { damping: 14 } });
  const pulse = 1 + 0.04 * Math.sin((frame / fps) * 6);
  const who = cast[0];
  const side = (v: VoteSide, color: string, bg: string, left: boolean) => (
    <div style={{ position: "absolute", top: 0, bottom: 0, left: left ? 0 : W / 2, width: W / 2, background: bg, overflow: "hidden" }}>
      <div style={{ position: "absolute", top: 330, width: "100%", textAlign: "center", transform: `scale(${s})` }}>
        <div style={{ fontFamily: FONT, fontSize: 150, color, WebkitTextStroke: "4px #111", lineHeight: 1 }}>{v.title}</div>
        <div style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900, fontSize: 36, color: "white",
          marginTop: 18, padding: "0 30px", lineHeight: 1.25 }}>{v.sub}</div>
      </div>
      {who ? (
        <div style={{ position: "absolute", left: "50%", top: 1480, transform: "translate(-50%, -100%)" }}>
          {who.sprite ? <Img src={staticFile(who.sprite)} style={{ height: H * 0.4, width: "auto" }} /> : <Placeholder name={who.name} h={H * 0.4} />}
        </div>
      ) : null}
    </div>
  );
  return (
    <AbsoluteFill>
      {side(vote.a, "#FFD60A", "linear-gradient(#5a0d16, #2a060b)", true)}
      {side(vote.b, "#4DA3FF", "linear-gradient(#0d3a20, #06190e)", false)}
      <div style={{ position: "absolute", left: W / 2 - 3, top: 300, bottom: 160, width: 6, background: "#FFD60A" }} />
      <div style={{ position: "absolute", top: 180, width: "100%", textAlign: "center", fontFamily: FONT, fontSize: 78,
        color: "#FFD60A", WebkitTextStroke: "3px #111" }}>COMMENT ONE WORD</div>
      <div style={{ position: "absolute", top: 1560, width: "100%", display: "flex", justifyContent: "center" }}>
        <div style={{ fontFamily: FONT, fontSize: 96, background: "#FFD60A", color: "#111", padding: "10px 70px",
          borderRadius: 26, transform: `scale(${pulse})`, boxShadow: "0 10px 0 rgba(0,0,0,.5)" }}>VOTE NOW</div>
      </div>
    </AbsoluteFill>
  );
};

const Captions: React.FC<{ words: CWord[]; perLine: number; position: number }> = ({ words, perLine, position }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const lines = toLines(words, perLine);
  const idx = lines.findIndex((l, i) => {
    const next = lines[i + 1];
    const end = next ? next[0].start : l[l.length - 1].end + 0.4;
    return t >= l[0].start && t < end;
  });
  if (idx < 0) return null;
  const line = lines[idx];
  const s = spring({ frame: frame - Math.round(line[0].start * fps), fps, config: { damping: 12, stiffness: 220 } });
  return (
    <div style={{ position: "absolute", left: 40, right: 40, top: `${position * 100}%`, textAlign: "center",
      transform: `translateY(-50%) scale(${interpolate(s, [0, 1], [0.7, 1])})` }}>
      {line.map((w, i) => (
        <span key={i} style={{ fontFamily: FONT, fontSize: 124, lineHeight: 1.05, margin: "0 14px", display: "inline-block",
          color: w.color ?? "white", WebkitTextStroke: "14px #0b0b0b", paintOrder: "stroke fill",
          textShadow: "0 8px 0 rgba(0,0,0,.55)", textTransform: "uppercase" }}>
          {w.w}
        </span>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- composition

export const CartoonShort: React.FC<CartoonProps> = (props) => {
  useFontReady();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const scene = props.scenes.find((s) => t >= s.start && t < s.end) ?? props.scenes[props.scenes.length - 1];
  if (!scene) return <AbsoluteFill style={{ background: "black" }} />;
  const local = t - scene.start;
  // quick zoom-punch on every scene change keeps the edit feeling fast
  const punch = interpolate(local, [0, 0.25], [1.08, 1], { extrapolateRight: "clamp" });
  const glowing = scene.cast.some((c) => c.anim?.includes("glow"));
  const flash = glowing ? interpolate(local, [0, 0.12, 0.6], [1, 0.9, 0], { extrapolateRight: "clamp" }) : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "black", overflow: "hidden" }}>
      {props.audioFile ? <Audio src={staticFile(props.audioFile)} /> : null}
      {scene.vote ? (
        <VoteCard vote={scene.vote} cast={scene.cast} sceneStart={scene.start} />
      ) : (
        <AbsoluteFill style={{ transform: `scale(${punch})` }}>
          <Background name={scene.background} sceneStart={scene.start} sceneEnd={scene.end} />
          {scene.cast.map((c, i) => (
            <Character key={`${c.name}-${i}`} c={c} sceneStart={scene.start} i={i} />
          ))}
          {scene.note ? <Note text={scene.note} sceneStart={scene.start} /> : null}
        </AbsoluteFill>
      )}
      {scene.hud && !scene.vote ? <Hud items={scene.hud} /> : null}
      {scene.banner && !scene.vote ? <Banner text={scene.banner} sceneStart={scene.start} /> : null}
      {!scene.vote ? <Captions words={props.words} perLine={props.wordsPerLine} position={props.captionPosition} /> : null}
      {flash > 0 ? <AbsoluteFill style={{ background: "white", opacity: flash }} /> : null}
    </AbsoluteFill>
  );
};
