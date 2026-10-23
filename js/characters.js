// Inline SVG drawings of the two characters: Bubu (brown bear) and Dudu (white panda).
// Original drawings in the Bubu & Dudu style: a big soft mochi-shaped head, stubby body,
// little nub arms, dot eyes, an open "ω" mouth, round cheeks and thick dark-brown outlines.
// Bubu's head and body are one continuous shape; Dudu's head sits on top of the body
// with a little dark collar underneath.

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
  blob(`M92 101 C91 ${101 + depth * 0.7} 95 ${101 + depth} 100 ${101 + depth} C105 ${101 + depth} 109 ${101 + depth * 0.7} 108 101 Z`, TONGUE) +
  line('M90 100 q5 5.5 10 0 q5 5.5 10 0', 3.5);

// Face features in head coordinates: eyes at (68, 96) and (132, 96), mouth below the centre.
const FACES = {
  happy: () => dot(68, 96, 7.5) + dot(132, 96, 7.5) + openMouth(20),
  sleepy: () =>
    line('M60 97 q8 6 16 0') + line('M124 97 q8 6 16 0') +
    line('M93 104 q3.5 4 7 0 q3.5 4 7 0', 3.5) +
    line('M172 16 h9 l-9 11 h9', 3.5) + line('M186 2 h7 l-7 9 h7', 3),
  hungry: () =>
    dot(68, 96, 8) + dot(132, 96, 8) + shine(71, 93, 2.6) + shine(135, 93, 2.6) +
    openMouth(27) +
    blob('M113 116 q8 12 0 17 q-8 -5 0 -17 z', WATER, 3),
  missyou: () =>
    dot(68, 96, 8.5) + dot(132, 96, 8.5) + shine(71, 92, 3) + shine(135, 92, 3) +
    blob('M138 104 q9 13 0 19 q-9 -6 0 -19 z', WATER, 3) +
    line('M90 113 q5 -5.5 10 0 q5 -5.5 10 0', 3.5),
  busy: () =>
    line('M60 96 h16') + line('M124 96 h16') +
    line('M93 108 h14', 3.5) +
    blob('M34 50 q8 12 0 17 q-8 -5 0 -17 z', WATER, 3),
  grumpy: () =>
    dot(68, 98, 6.5) + dot(132, 98, 6.5) +
    line('M54 82 l20 7') + line('M146 82 l-20 7') +
    line('M90 114 q10 -9 20 0', 3.5),
};

const cheeks = (c) =>
  `<circle cx="46" cy="116" r="15" fill="${c.cheek}"/><circle cx="154" cy="116" r="15" fill="${c.cheek}"/>`;

// The top and sides of the head, shared by both characters.
const HEAD_TOP = 'M100 8 C152 8 186 34 187 82';
const headShape = (fill) =>
  `<path fill="${fill}" d="${HEAD_TOP} C188 120 166 140 100 141 C34 140 12 120 13 82 C14 34 48 8 100 8 Z"/>`;

function bubuParts(c) {
  const ears =
    `<circle cx="44" cy="30" r="20" fill="${c.fur}"/><circle cx="156" cy="30" r="20" fill="${c.fur}"/>` +
    `<circle cx="46" cy="33" r="12.5" fill="${INK}" stroke="none"/><circle cx="154" cy="33" r="12.5" fill="${INK}" stroke="none"/>`;
  const arms =
    `<ellipse cx="30" cy="152" rx="21" ry="13" fill="${c.fur}" transform="rotate(-12 30 152)"/>` +
    `<ellipse cx="170" cy="152" rx="21" ry="13" fill="${c.fur}" transform="rotate(12 170 152)"/>`;
  // One silhouette: head, then down the body to two little feet and back up, no chin line.
  const silhouette =
    `<path fill="${c.fur}" d="${HEAD_TOP} C188 114 172 134 154 140 ` +
    'C164 158 162 182 154 196 C150 205 132 206 124 203 C114 201 106 198 100 195 ' +
    'C94 198 86 201 76 203 C68 206 50 205 46 196 C38 182 36 158 46 140 ' +
    'C28 134 12 114 13 82 C14 34 48 8 100 8 Z"/>';
  return { ears, body: arms + silhouette, head: headShape(c.fur), collar: '' };
}

function duduParts(c) {
  const ears = `<circle cx="46" cy="28" r="21" fill="${INK}"/><circle cx="172" cy="50" r="20" fill="${INK}"/>`;
  const arms =
    `<ellipse cx="32" cy="154" rx="21" ry="13" fill="${c.fur}" transform="rotate(-12 32 154)"/>` +
    `<ellipse cx="168" cy="154" rx="21" ry="13" fill="${c.fur}" transform="rotate(12 168 154)"/>`;
  const torso =
    `<path fill="${c.fur}" d="M50 128 C42 156 44 182 52 196 C64 205 86 204 100 199 C114 204 136 205 148 196 C156 182 158 156 150 128 Z"/>`;
  const feet =
    `<ellipse cx="70" cy="201" rx="12" ry="7" fill="${INK}"/><ellipse cx="130" cy="201" rx="12" ry="7" fill="${INK}"/>`;
  // Little dark bow just under the chin.
  const collar = `<path d="M84 139 Q90 152 100 146 Q110 152 116 139 Q100 145 84 139 Z" fill="${INK}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>`;
  return { ears, body: arms + torso + feet + headShape(c.fur), head: headShape(c.fur), collar };
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
  const stroke = `stroke="${INK}" stroke-width="5.5" stroke-linejoin="round" stroke-linecap="round"`;
  const a11y = opts.label
    ? `role="img" aria-label="${opts.label.replace(/"/g, '&quot;')}"`
    : 'aria-hidden="true" focusable="false"';

  if (opts.faceOnly) {
    return `<svg viewBox="4 -2 196 150" ${a11y}><g ${stroke}>${parts.ears}${parts.head}</g>${cheeks(c)}${face}</svg>`;
  }
  return `<svg viewBox="0 0 200 210" ${a11y}><g ${stroke}>${parts.ears}${parts.body}</g>${parts.collar}${cheeks(c)}${face}</svg>`;
}
