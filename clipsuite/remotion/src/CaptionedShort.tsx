import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export type Word = { w: string; start: number; end: number };

export type ShortProps = {
  /** path inside remotion/public, e.g. "clips/job-01.mp4" (ClipSuite copies it there) */
  videoFile: string;
  durationInSeconds: number;
  title: string;
  words: Word[];
  accent: string;
  /** 0..1 – vertical position of the caption line */
  captionPosition: number;
  wordsPerLine: number;
  uppercase: boolean;
};

/** Split words into short lines, breaking on pauses and sentence ends (mirrors captions.py). */
const toLines = (words: Word[], perLine: number): Word[][] => {
  const lines: Word[][] = [];
  let cur: Word[] = [];
  for (const w of words) {
    const prev = cur[cur.length - 1];
    if (prev && (cur.length >= perLine || w.start - prev.end > 0.6 || /[.?!]$/.test(prev.w))) {
      lines.push(cur);
      cur = [];
    }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  return lines;
};

const Captions: React.FC<{ props: ShortProps }> = ({ props }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const lines = toLines(props.words, props.wordsPerLine);
  const line = lines.find((l, i) => {
    const next = lines[i + 1];
    return t >= l[0].start && t < (next ? Math.min(next[0].start, l[l.length - 1].end + 0.5) : l[l.length - 1].end + 0.5);
  });
  if (!line) return null;
  const lineStartFrame = Math.round(line[0].start * fps);
  const enter = spring({ frame: frame - lineStartFrame, fps, config: { damping: 14, stiffness: 180 } });

  return (
    <div
      style={{
        position: "absolute",
        left: 60,
        right: 60,
        top: `${props.captionPosition * 100}%`,
        transform: `translateY(-50%) scale(${interpolate(enter, [0, 1], [0.85, 1])})`,
        textAlign: "center",
        fontFamily: "Montserrat, 'Arial Black', sans-serif",
        fontWeight: 900,
        fontSize: 86,
        lineHeight: 1.1,
        color: "white",
        textTransform: props.uppercase ? "uppercase" : "none",
        WebkitTextStroke: "3px black",
        textShadow: "0 8px 0 rgba(0,0,0,.6), 0 0 24px rgba(0,0,0,.6)",
      }}
    >
      {line.map((w, i) => {
        const active = t >= w.start && t < (line[i + 1]?.start ?? w.end + 0.5);
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              margin: "0 16px",
              transformOrigin: "50% 60%",
              color: active ? props.accent : "white",
              transform: active ? "scale(1.06)" : "none",
            }}
          >
            {w.w}
          </span>
        );
      })}
    </div>
  );
};

const Title: React.FC<{ text: string; accent: string }> = ({ text, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!text) return null;
  const inS = spring({ frame, fps, config: { damping: 12 } });
  const out = interpolate(frame, [fps * 2.6, fps * 3], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  if (out <= 0) return null;
  return (
    <div
      style={{
        position: "absolute",
        top: 230,
        left: 70,
        right: 70,
        textAlign: "center",
        opacity: out,
        transform: `translateY(${interpolate(inS, [0, 1], [-60, 0])}px)`,
      }}
    >
      <span
        style={{
          display: "inline-block",
          background: "rgba(0,0,0,.82)",
          borderBottom: `10px solid ${accent}`,
          color: "white",
          padding: "22px 34px",
          borderRadius: 18,
          fontFamily: "Montserrat, 'Arial Black', sans-serif",
          fontWeight: 900,
          fontSize: 68,
          lineHeight: 1.1,
        }}
      >
        {text}
      </span>
    </div>
  );
};

const Progress: React.FC<{ accent: string }> = ({ accent }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: 0, bottom: 0, height: 12, width: `${(frame / durationInFrames) * 100}%`, background: accent }} />
  );
};

export const CaptionedShort: React.FC<ShortProps> = (props) => (
  <AbsoluteFill style={{ backgroundColor: "black" }}>
    {props.videoFile ? (
      <OffthreadVideo src={staticFile(props.videoFile)} />
    ) : (
      <AbsoluteFill style={{ background: "linear-gradient(160deg,#333,#111)" }} />
    )}
    <Captions props={props} />
    <Title text={props.title} accent={props.accent} />
    <Progress accent={props.accent} />
  </AbsoluteFill>
);
