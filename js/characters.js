// Inline SVG drawings of the two characters: Bubu (brown bear) and Dudu (white panda).
// Original drawings in the Bubu & Dudu style: chubby bodies, dot eyes, rosy cheeks,
// thick dark-brown outlines.

export const INK = '#4B2A20';
const TONGUE = '#F08A8E';
const WATER = '#BFE3F5';

export const CHARACTERS = {
  bubu: { label: 'Bubu', species: 'brown bear', fur: '#D9A68C', limbs: '#D9A68C', ears: '#D9A68C', earInner: INK, cheek: '#F8C383' },
  dudu: { label: 'Dudu', species: 'white panda', fur: '#FFFFFF', limbs: '#FFFFFF', ears: INK, earInner: null, cheek: '#FBB9B9', feet: INK, collar: true },
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
const line = (d, w = 5) =>
  `<path d="${d}" fill="none" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
const blob = (d, fill, w = 4) =>
  `<path d="${d}" fill="${fill}" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;

const FACES = {
  happy: () =>
    dot(72, 92, 7.5) + dot(128, 92, 7.5) +
    blob('M90 107 q10 18 20 0', TONGUE) +
    line('M86 104 q7 7 14 0 q7 7 14 0', 4.5),
  sleepy: () =>
    line('M63 93 q9 7 18 0') + line('M119 93 q9 7 18 0') +
    line('M94 110 q6 4 12 0', 4.5) +
    line('M176 70 h10 l-10 12 h10', 3.5) + line('M186 48 h8 l-8 10 h8', 3),
  hungry: () =>
    dot(72, 92, 8) + dot(128, 92, 8) + shine(75, 89, 2.6) + shine(131, 89, 2.6) +
    blob('M86 102 q14 30 28 0 z', TONGUE) +
    blob('M114 118 q9 13 0 19 q-9 -6 0 -19 z', WATER, 3),
  missyou: () =>
    dot(72, 92, 8.5) + dot(128, 92, 8.5) + shine(75, 88, 3) + shine(131, 88, 3) +
    blob('M134 100 q10 14 0 21 q-10 -7 0 -21 z', WATER, 3) +
    line('M88 116 q6 -7 12 0 q6 -7 12 0', 4.5),
  busy: () =>
    line('M64 92 h16') + line('M120 92 h16') +
    line('M92 111 h16', 4.5) +
    blob('M170 46 q10 14 0 21 q-10 -7 0 -21 z', WATER, 3),
  grumpy: () =>
    dot(72, 94, 6.5) + dot(128, 94, 6.5) +
    line('M60 78 l20 8') + line('M140 78 l-20 8') +
    line('M88 117 q12 -11 24 0', 4.5),
};

function head(c) {
  const ears = c.earInner
    ? `<circle cx="46" cy="40" r="24" fill="${c.ears}"/><circle cx="154" cy="40" r="24" fill="${c.ears}"/>`
    : `<circle cx="44" cy="40" r="24" fill="${c.ears}"/><circle cx="158" cy="46" r="24" fill="${c.ears}"/>`;
  const inner = c.earInner
    ? `<circle cx="46" cy="40" r="12" fill="${c.earInner}" stroke="none"/><circle cx="154" cy="40" r="12" fill="${c.earInner}" stroke="none"/>`
    : '';
  return { ears, inner, skull: `<ellipse cx="100" cy="88" rx="82" ry="62" fill="${c.fur}"/>` };
}

/**
 * Returns an SVG string for a character.
 * @param {'bubu'|'dudu'} kind
 * @param {string} mood one of MOOD_KEYS
 * @param {{faceOnly?: boolean, label?: string}} [opts]
 */
export function characterSVG(kind, mood = 'happy', opts = {}) {
  const c = CHARACTERS[kind] ?? CHARACTERS.bubu;
  const face = (FACES[mood] ?? FACES.happy)();
  const h = head(c);
  const stroke = `stroke="${INK}" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"`;
  const cheeks = `<ellipse cx="50" cy="110" rx="17" ry="13" fill="${c.cheek}"/><ellipse cx="150" cy="110" rx="17" ry="13" fill="${c.cheek}"/>`;
  const a11y = opts.label
    ? `role="img" aria-label="${opts.label.replace(/"/g, '&quot;')}"`
    : 'aria-hidden="true" focusable="false"';

  if (opts.faceOnly) {
    return `<svg viewBox="10 0 190 158" ${a11y}><g ${stroke}>${h.ears}${h.inner}${h.skull}</g>${cheeks}${face}</svg>`;
  }

  const feet = c.feet ?? c.limbs;
  const body =
    `<ellipse cx="78" cy="194" rx="18" ry="10" fill="${feet}"/>` +
    `<ellipse cx="122" cy="194" rx="18" ry="10" fill="${feet}"/>` +
    `<ellipse cx="100" cy="160" rx="46" ry="36" fill="${c.fur}"/>` +
    `<ellipse cx="50" cy="150" rx="19" ry="11" fill="${c.limbs}" transform="rotate(-25 50 150)"/>` +
    `<ellipse cx="150" cy="150" rx="19" ry="11" fill="${c.limbs}" transform="rotate(25 150 150)"/>`;
  const collar = c.collar
    ? `<path d="M84 146 q16 10 32 0 l-4 12 q-12 6 -24 0 z" fill="${INK}"/>`
    : '';
  return `<svg viewBox="0 0 200 210" ${a11y}><g ${stroke}>${h.ears}${h.inner}${body}${h.skull}</g>${collar}${cheeks}${face}</svg>`;
}
