import { Composition } from "remotion";
import { CaptionedShort, type ShortProps } from "./CaptionedShort";

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

export const RemotionRoot: React.FC = () => (
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
);
