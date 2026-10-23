// Inline SVG drawings of the two characters: Bubu (brown bear) and Dudu (white panda).
// Original drawings in the Bubu & Dudu style: a big soft head that is widest down at the
// cheeks, a short chunky body, little nub arms, dot eyes, an open "ω" mouth, round cheeks
// and dark-brown outlines. Bubu's head and body are one continuous shape; Dudu's head sits
// on top of the body with a little dark bow underneath.

export const INK = '#4B2520';
const TONGUE = '#F28C92';
const WATER = '#BFE3F5';

export const CHARACTERS = {
  bubu: { label: 'Bubu', species: 'brown bear', fur: '#DBA68B', cheek: '#F8C784' },
  dudu: { label: 'Dudu', species: 'white panda', fur: '#FFFFFF', cheek: '#FBB8B8' },
};

export const MOODS = {
  happy: { label: 'Happy', tint: '#FFE7A8' },
  sleepy: { label: 'Sleepy', tint: '#DCE6FF' },
  hungry: { label: 'Hungry', tint: '#FFDCC7' },
  missyou: { label: 'Missing you', tint: '#FFD3DD' },
  busy: { label: 'Busy', tint: '#E4E8EB' },
  grumpy: { label: 'Grumpy', tint: '#EADDF6' },
};

export const MOOD_KEYS = Object.keys(MOODS);

const dot = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${INK}"/>`;
const shine = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#FFFFFF"/>`;
const line = (d, w = 4.5) =>
  `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
const blob = (d, fill, w = 3.5) =>
  `<path d="${d}" fill="${fill}" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;

// Open mouth: a small "ω" on top of a U filled with tongue. `depth` is how far it drops.
const openMouth = (depth) =>
  blob(`M93 97 C92 ${97 + depth * 0.7} 96 ${97 + depth} 100 ${97 + depth} C104 ${97 + depth} 108 ${97 + depth * 0.7} 107 97 Z`, TONGUE, 3.2) +
  line('M91.5 96 q4.25 5 8.5 0 q4.25 5 8.5 0', 3.2);

// Face features in head coordinates: eyes at (67, 92) and (133, 92), mouth just below.
const FACES = {
  happy: () => dot(67, 92, 8.5) + dot(133, 92, 8.5) + openMouth(19),
  sleepy: () =>
    line('M59 93 q8 6 16 0') + line('M125 93 q8 6 16 0') +
    line('M93 100 q3.5 4 7 0 q3.5 4 7 0', 3.2) +
    line('M176 -6 h9 l-9 11 h9', 3.5) + line('M190 -20 h7 l-7 9 h7', 3),
  hungry: () =>
    dot(67, 92, 9) + dot(133, 92, 9) + shine(70, 88.5, 3) + shine(136, 88.5, 3) +
    openMouth(25) +
    blob('M112 110 q8 12 0 17 q-8 -5 0 -17 z', WATER, 3),
  missyou: () =>
    dot(67, 92, 9.5) + dot(133, 92, 9.5) + shine(70, 88, 3.4) + shine(136, 88, 3.4) +
    blob('M140 100 q9 13 0 19 q-9 -6 0 -19 z', WATER, 3) +
    line('M90 108 q5 -5.5 10 0 q5 -5.5 10 0', 3.2),
  busy: () =>
    line('M59 92 h16') + line('M125 92 h16') +
    line('M93 104 h14', 3.2) +
    blob('M28 52 q8 12 0 17 q-8 -5 0 -17 z', WATER, 3),
  grumpy: () =>
    dot(67, 94, 7.5) + dot(133, 94, 7.5) +
    line('M54 78 l20 7') + line('M146 78 l-20 7') +
    line('M90 110 q10 -9 20 0', 3.2),
};

const cheeks = (c) =>
  `<circle cx="40" cy="110" r="17" fill="${c.cheek}"/><circle cx="160" cy="110" r="17" fill="${c.cheek}"/>`;

// Head: narrower at the top, widest down at cheek level, soft flat-ish bottom.
const HEAD_TOP_RIGHT = 'M100 -12 C138 -12 166 4 178 30 C188 52 193 82 190 104';
const HEAD_LEFT_TOP = 'C7 82 12 52 22 30 C34 4 62 -12 100 -12 Z';
const headShape = (fill) =>
  `<path fill="${fill}" d="${HEAD_TOP_RIGHT} C187 124 160 136 100 136 C40 136 13 124 10 104 ${HEAD_LEFT_TOP}"/>`;

function bubuParts(c) {
  const ears =
    `<circle cx="40" cy="12" r="20" fill="${c.fur}"/><circle cx="160" cy="12" r="20" fill="${c.fur}"/>` +
    `<circle cx="42" cy="14" r="13" fill="${INK}" stroke="none"/><circle cx="158" cy="14" r="13" fill="${INK}" stroke="none"/>`;
  const arms =
    `<ellipse cx="32" cy="148" rx="21" ry="13" fill="${c.fur}" transform="rotate(-10 32 148)"/>` +
    `<ellipse cx="168" cy="148" rx="21" ry="13" fill="${c.fur}" transform="rotate(10 168 148)"/>`;
  // One silhouette: head, then down a short chunky body to two feet and back up. No chin line.
  const silhouette =
    `<path fill="${c.fur}" d="${HEAD_TOP_RIGHT} C189 122 170 132 150 136 ` +
    'C159 154 159 188 152 204 C148 214 134 216 126 212 C116 208 108 202 100 195 ' +
    'C92 202 84 208 74 212 C66 216 52 214 48 204 C41 188 41 154 50 136 ' +
    `C30 132 11 122 10 104 ${HEAD_LEFT_TOP}"/>`;
  // Where the arms meet the head there's a short stroke on each side, not a full chin.
  const armLines = line('M18 134 Q36 141 56 139', 4.5) + line('M144 139 Q164 141 182 134', 4.5);
  return { ears, body: arms + silhouette, head: headShape(c.fur), extra: armLines };
}

function duduParts(c) {
  const ears = `<circle cx="40" cy="8" r="21" fill="${INK}"/><circle cx="178" cy="36" r="20" fill="${INK}"/>`;
  const arms =
    `<ellipse cx="36" cy="152" rx="21" ry="13" fill="${c.fur}" transform="rotate(-10 36 152)"/>` +
    `<ellipse cx="164" cy="152" rx="21" ry="13" fill="${c.fur}" transform="rotate(10 164 152)"/>`;
  const torso =
    `<path fill="${c.fur}" d="M54 128 C44 156 44 190 54 206 C64 216 86 214 100 208 C114 214 136 216 146 206 C156 190 156 156 146 128 Z"/>`;
  const feet =
    `<ellipse cx="72" cy="210" rx="13" ry="7" fill="${INK}"/><ellipse cx="128" cy="210" rx="13" ry="7" fill="${INK}"/>`;
  // Little dark bow just under the chin.
  const bow =
    `<path d="M100 141 L86 135 Q80 143 87 150 Z M100 141 L114 135 Q120 143 113 150 Z" fill="${INK}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>` +
    dot(100, 141, 5);
  return { ears, body: arms + torso + feet + headShape(c.fur), head: headShape(c.fur), extra: bow };
}

/**
 * Returns an SVG string for a character.
 * @param {'bubu'|'dudu'} kind
 * @param {string} mood one of MOOD_KEYS
 * @param {{faceOnly?: boolean, label?: string}} [opts]
 */
export function characterSVG(kind, mood = 'happy', opts = {}) {
  const c = CHARACTERS[kind] ?? CHARACTERS.bubu;
  const parts = (kind === 'dudu' ? duduParts : bubuParts)(c);
  const face = (FACES[mood] ?? FACES.happy)();
  const stroke = `stroke="${INK}" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round"`;
  const a11y = opts.label
    ? `role="img" aria-label="${opts.label.replace(/"/g, '&quot;')}"`
    : 'aria-hidden="true" focusable="false"';

  if (opts.faceOnly) {
    return `<svg viewBox="4 -24 196 166" ${a11y}><g ${stroke}>${parts.ears}${parts.head}</g>${cheeks(c)}${face}</svg>`;
  }
  return `<svg viewBox="0 -24 200 244" ${a11y}><g ${stroke}>${parts.ears}${parts.body}</g>${parts.extra}${cheeks(c)}${face}</svg>`;
}
