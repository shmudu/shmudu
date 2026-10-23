import assert from 'node:assert/strict';
import { test, mock } from 'node:test';

const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
};

const { createBackend } = await import('../js/backend-demo.js');

test('demo flow: profile, pair, send, partner replies, status', async () => {
  mock.timers.enable({ apis: ['setTimeout'] });
  store.clear();
  const backend = createBackend();
  let snap;
  backend.start((s) => { snap = s; });
  assert.equal(snap.me, null);

  await backend.setProfile({ name: 'Mochi', character: 'dudu' });
  assert.deepEqual(snap.me, { uid: 'me', name: 'Mochi', character: 'dudu' });

  const code = await backend.createCouple();
  assert.match(code, /^\d{6}$/);
  assert.equal(snap.waitingCode, code);
  assert.equal(snap.partner, null);
  mock.timers.tick(4000);
  assert.equal(snap.partner.character, 'bubu');
  assert.equal(snap.waitingCode, null);

  const before = snap.events.length;
  await backend.send('poke');
  assert.equal(snap.events[0].kind, 'poke');
  assert.equal(snap.events[0].from, 'me');
  assert.equal(snap.counts.poke, 1);
  mock.timers.tick(2200);
  assert.equal(snap.events.length, before + 2);
  assert.equal(snap.events[0].from, 'partner');

  await backend.setStatus({ mood: 'hungry', activity: 'Eating', note: 'dumplings' });
  assert.equal(snap.statuses.me.mood, 'hungry');
  assert.equal(snap.events[0].kind, 'status');

  // Survives a reload.
  const again = createBackend();
  let snap2;
  again.start((s) => { snap2 = s; });
  assert.equal(snap2.partner.name, 'Bubu');
  assert.equal(snap2.statuses.me.note, 'dumplings');

  await backend.joinCouple('12').then(() => assert.fail('should reject'), (e) => assert.match(e.message, /6 digits/));
  mock.timers.reset();
});
