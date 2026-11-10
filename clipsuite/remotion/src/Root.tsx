import { Composition } from "remotion";
import { CaptionedShort, type ShortProps } from "./CaptionedShort";
import { CartoonShort, type CartoonProps } from "./cartoon/CartoonShort";

const FPS = 30;

const sample: ShortProps = {
  videoFile: "",
  durationInSeconds: 6,
  title: "Your hook title here",
  words: [
    { w: "This", start: 0.2, end: 0.5 },
    { w: "is", start: 0.5, end: 0.7 },
    { w: "a", start: 0.7, end: 0.8 },
    { w: "ClipSuite", start: 0.8, end: 1.4 },
    { w: "preview.", start: 1.4, end: 2.0 },
    { w: "Render", start: 2.4, end: 2.8 },
    { w: "a", start: 2.8, end: 2.9 },
    { w: "clip", start: 2.9, end: 3.3 },
    { w: "to", start: 3.3, end: 3.5 },
    { w: "see", start: 3.5, end: 3.8 },
    { w: "it", start: 3.8, end: 4.0 },
    { w: "here.", start: 4.0, end: 4.6 },
  ],
  accent: "#FFE500",
  captionPosition: 0.7,
  wordsPerLine: 3,
  uppercase: true,
};

const cartoonSample: CartoonProps = {
  audioFile: "",
  durationInSeconds: 8,
  wordsPerLine: 2,
  captionPosition: 0.66,
  scenes: [
    { start: 0, end: 4, background: "bedroom", hud: [{ label: "EPISODE", value: "1" }, { label: "GLOW-UP", value: "0%", color: "#46D160" }],
      banner: "30 DAYS TO WIN HER", cast: [{ sprite: "", name: "guy", x: 0.5, height: 0.62, anim: ["enter"] }] },
    { start: 4, end: 8, background: "gym", note: "NO.", cast: [{ sprite: "", name: "guy", x: 0.4, height: 0.62, anim: ["shake"] }] },
  ],
  words: [
    { w: "Meet", start: 0.3, end: 0.6 }, { w: "Dave.", start: 0.6, end: 1.1, color: "#4DA3FF" },
    { w: "Day", start: 4.2, end: 4.5 }, { w: "one", start: 4.5, end: 4.8 }, { w: "at", start: 4.8, end: 5.0 },
    { w: "the", start: 5.0, end: 5.1 }, { w: "gym.", start: 5.1, end: 5.6, color: "#FF3B30" },
  ],
};

export const RemotionRoot: React.FC = () => (
  <>
  <Composition
    id="CartoonShort"
    component={CartoonShort}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={Math.round(cartoonSample.durationInSeconds * FPS)}
    defaultProps={cartoonSample}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, Math.round(props.durationInSeconds * FPS)),
    })}
  />
  <Composition
    id="CaptionedShort"
    component={CaptionedShort}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={Math.round(sample.durationInSeconds * FPS)}
    defaultProps={sample}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, Math.round(props.durationInSeconds * FPS)),
    })}
  />
  </>
);
