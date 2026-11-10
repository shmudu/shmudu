import React from "react";
import { useCurrentFrame } from "remotion";

/**
 * Built-in moody backgrounds (1080x1920), drawn as SVG so they stay crisp and need no assets.
 * Characters stand on the floor around y = 1750. Replace any of them with your own art via
 * `clipsuite background add bedroom my-bedroom.png`.
 */

const W = 1080;
const H = 1920;

export const Bedroom: React.FC = () => {
  const f = useCurrentFrame();
  const flicker = 0.85 + 0.15 * Math.sin(f / 7) * Math.sin(f / 13);
  const screen = 0.75 + 0.25 * Math.abs(Math.sin(f / 19));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      <defs>
        <linearGradient id="bWall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#120c22" />
          <stop offset="1" stopColor="#2a1b45" />
        </linearGradient>
        <linearGradient id="bSky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#070a1c" />
          <stop offset="1" stopColor="#1f2858" />
        </linearGradient>
        <linearGradient id="bFloor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2b2033" />
          <stop offset="1" stopColor="#120d17" />
        </linearGradient>
        <radialGradient id="bScreenGlow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#38d6ff" stopOpacity="0.45" />
          <stop offset="1" stopColor="#38d6ff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="bHeartGlow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#ff2d75" stopOpacity="0.5" />
          <stop offset="1" stopColor="#ff2d75" stopOpacity="0" />
        </radialGradient>
        <filter id="bBlur"><feGaussianBlur stdDeviation="10" /></filter>
      </defs>
      <rect width={W} height={H} fill="url(#bWall)" />
      {/* purple LED strip */}
      <rect x="0" y="96" width={W} height="10" fill="#b44dff" opacity={0.9 * flicker} />
      <rect x="0" y="80" width={W} height="60" fill="#b44dff" opacity={0.25 * flicker} filter="url(#bBlur)" />
      {/* window with city at night */}
      <rect x="90" y="260" width="430" height="520" rx="10" fill="#0b0816" />
      <rect x="110" y="280" width="390" height="480" fill="url(#bSky)" />
      <circle cx="420" cy="360" r="38" fill="#f4f1d0" opacity="0.9" />
      {[0, 1, 2, 3, 4, 5, 6].map((i) => {
        const bw = 52 + (i % 3) * 10;
        const bh = 140 + ((i * 53) % 170);
        const x = 110 + i * 56;
        return (
          <g key={i}>
            <rect x={x} y={760 - bh} width={bw} height={bh} fill="#0c0f24" />
            {[0, 1, 2, 3, 4].map((j) => (
              <rect key={j} x={x + 10 + (j % 2) * 22} y={760 - bh + 18 + j * 26} width="10" height="12"
                fill="#ffd36b" opacity={(i + j) % 3 === 0 ? 0.9 : 0.15} />
            ))}
          </g>
        );
      })}
      <rect x="300" y="280" width="10" height="480" fill="#0b0816" />
      <rect x="110" y="515" width="390" height="10" fill="#0b0816" />
      {/* neon heart */}
      <circle cx="800" cy="470" r="200" fill="url(#bHeartGlow)" opacity={flicker} />
      <path d="M800 560 C 700 490, 690 400, 750 385 C 780 378, 795 395, 800 410 C 805 395, 820 378, 850 385 C 910 400, 900 490, 800 560 Z"
        fill="none" stroke="#ff4f8f" strokeWidth="12" opacity={flicker} />
      {/* bed (left) */}
      <rect x="-20" y="1050" width="560" height="200" rx="20" fill="#1a1226" />
      <rect x="-20" y="1210" width="600" height="230" rx="18" fill="#3b3550" />
      <path d="M-20 1230 C 120 1180, 260 1290, 400 1225 C 470 1195, 540 1240, 580 1220 L 580 1440 L -20 1440 Z" fill="#5a5274" />
      <ellipse cx="120" cy="1215" rx="110" ry="40" fill="#8a84a3" />
      <circle cx="300" cy="1300" r="22" fill="#9c8b4a" opacity="0.6" />
      <circle cx="420" cy="1340" r="16" fill="#9c8b4a" opacity="0.5" />
      {/* desk + monitor (right) */}
      <circle cx="900" cy="1080" r="260" fill="url(#bScreenGlow)" opacity={screen} />
      <rect x="760" y="960" width="280" height="170" rx="10" fill="#0d0d14" />
      <rect x="772" y="972" width="256" height="146" fill="#2ec8f0" opacity={screen} />
      <rect x="880" y="1130" width="40" height="50" fill="#0d0d14" />
      <rect x="700" y="1180" width="400" height="26" fill="#2a1f33" />
      <rect x="720" y="1206" width="22" height="260" fill="#1c1424" />
      <rect x="1050" y="1206" width="22" height="260" fill="#1c1424" />
      {[0, 1, 2].map((i) => (
        <rect key={i} x={730 + i * 30} y={1130} width="22" height="50" rx="5" fill="#3ddc6e" />
      ))}
      {/* floor + clutter */}
      <rect x="0" y="1440" width={W} height={H - 1440} fill="url(#bFloor)" />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line key={i} x1={W / 2} y1="1440" x2={-600 + i * 460} y2={H} stroke="#000" strokeOpacity="0.18" strokeWidth="3" />
      ))}
      <rect x="70" y="1700" width="230" height="40" rx="6" fill="#c9a36b" transform="rotate(-6 185 1720)" />
      <ellipse cx="880" cy="1760" rx="120" ry="30" fill="#4a3d5c" />
      <rect x="640" y="1810" width="24" height="54" rx="6" fill="#3ddc6e" transform="rotate(70 652 1837)" />
      <rect x="200" y="1830" width="24" height="54" rx="6" fill="#3ddc6e" transform="rotate(-40 212 1857)" />
    </svg>
  );
};

export const Gym: React.FC = () => {
  const f = useCurrentFrame();
  const pulse = 0.8 + 0.2 * Math.sin(f / 9);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      <defs>
        <linearGradient id="gWall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#141417" />
          <stop offset="1" stopColor="#2b2b31" />
        </linearGradient>
        <linearGradient id="gFloor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#202024" />
          <stop offset="1" stopColor="#0b0b0d" />
        </linearGradient>
        <filter id="gBlur"><feGaussianBlur stdDeviation="14" /></filter>
      </defs>
      <rect width={W} height={H} fill="url(#gWall)" />
      {[0, 1, 2, 3].map((i) => (
        <line key={i} x1={i * 270 + 135} y1="0" x2={i * 270 + 135} y2="1440" stroke="#000" strokeOpacity="0.25" strokeWidth="4" />
      ))}
      {/* red light strips */}
      {[60, 1010].map((x) => (
        <g key={x}>
          <rect x={x} y="160" width="12" height="1200" fill="#ff2a2a" opacity={pulse} />
          <rect x={x - 30} y="160" width="72" height="1200" fill="#ff2a2a" opacity={0.3 * pulse} filter="url(#gBlur)" />
        </g>
      ))}
      {/* sign */}
      <rect x="230" y="230" width="620" height="150" rx="14" fill="#0e0e10" stroke="#ff2a2a" strokeWidth="6" opacity={pulse} />
      <text x="540" y="335" textAnchor="middle" fontFamily="Anton, Impact, sans-serif" fontSize="92" fill="#ff3b3b"
        letterSpacing="4" opacity={pulse}>NO EXCUSES</text>
      {/* mirror */}
      <rect x="300" y="470" width="480" height="760" rx="8" fill="#3a3f4a" opacity="0.55" />
      <line x1="360" y1="520" x2="520" y2="760" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="18" />
      {/* squat rack (left) */}
      <rect x="110" y="600" width="26" height="840" fill="#3c3c44" />
      <rect x="250" y="600" width="26" height="840" fill="#3c3c44" />
      <rect x="40" y="900" width="320" height="14" fill="#9a9aa5" />
      <rect x="40" y="840" width="30" height="130" rx="6" fill="#111" />
      <rect x="330" y="840" width="30" height="130" rx="6" fill="#111" />
      {/* dumbbell rack (right) */}
      <rect x="760" y="1150" width="300" height="20" fill="#3c3c44" />
      <rect x="760" y="1290" width="300" height="20" fill="#3c3c44" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <rect x={780 + i * 70} y="1112" width="50" height="40" rx="8" fill="#18181b" />
          <rect x={780 + i * 70} y="1250" width="50" height="40" rx="8" fill="#18181b" />
        </g>
      ))}
      {/* floor */}
      <rect x="0" y="1440" width={W} height={H - 1440} fill="url(#gFloor)" />
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <line key={i} x1={W / 2} y1="1440" x2={-700 + i * 410} y2={H} stroke="#000" strokeOpacity="0.35" strokeWidth="3" />
      ))}
      <line x1="0" y1="1600" x2={W} y2="1600" stroke="#000" strokeOpacity="0.3" strokeWidth="3" />
      {/* bench + plates */}
      <rect x="40" y="1560" width="300" height="40" rx="12" fill="#7a1010" />
      <rect x="80" y="1600" width="20" height="120" fill="#222" />
      <rect x="290" y="1600" width="20" height="120" fill="#222" />
      <circle cx="930" cy="1760" r="70" fill="#141416" stroke="#333" strokeWidth="10" />
      <circle cx="930" cy="1760" r="14" fill="#555" />
    </svg>
  );
};

export const Plain: React.FC<{ color?: string }> = ({ color = "#1a1426" }) => (
  <div style={{ position: "absolute", inset: 0, background: `radial-gradient(circle at 50% 35%, #3a2d55, ${color})` }} />
);

export const BUILT_IN: Record<string, React.FC> = { bedroom: Bedroom, gym: Gym, plain: Plain };
