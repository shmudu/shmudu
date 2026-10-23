import assert from 'node:assert/strict';
import { test } from 'node:test';
import { characterSVG, CHARACTERS, MOOD_KEYS } from '../js/characters.js';

test('draws every character in every mood', () => {
  for (const kind of Object.keys(CHARACTERS)) {
    for (const mood of MOOD_KEYS) {
      for (const faceOnly of [false, true]) {
        const svg = characterSVG(kind, mood, { faceOnly });
        assert.match(svg, /^<svg [^>]*viewBox=/);
        assert.match(svg, /<\/svg>$/);
        assert.equal((svg.match(/<svg/g) || []).length, 1);
      }
    }
  }
});

test('labels are escaped and decorative art is hidden', () => {
  assert.match(characterSVG('bubu', 'happy', { label: 'Bubu "the" bear' }), /aria-label="Bubu &quot;the&quot; bear"/);
  assert.match(characterSVG('dudu', 'happy'), /aria-hidden="true"/);
});

test('unknown inputs fall back safely', () => {
  assert.equal(characterSVG('nope', 'nope'), characterSVG('bubu', 'happy'));
});
