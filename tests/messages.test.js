import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EVENT_KINDS, pushText, receivedText, sentText, timeAgo } from '../js/messages.js';

test('timeAgo buckets', () => {
  const now = 1_000_000_000_000;
  assert.equal(timeAgo(now - 10_000, now), 'just now');
  assert.equal(timeAgo(now - 5 * 60_000, now), '5 min ago');
  assert.equal(timeAgo(now - 3 * 3_600_000, now), '3 hr ago');
  assert.equal(timeAgo(now - 30 * 3_600_000, now), 'yesterday');
  assert.equal(timeAgo(now - 4 * 86_400_000, now), '4 days ago');
  assert.equal(timeAgo(0, now), 'a while ago');
  assert.equal(timeAgo(now + 5000, now), 'just now');
});

test('every event kind has sent, received and push text', () => {
  for (const kind of EVENT_KINDS) {
    assert.match(sentText(kind, 'Dudu', { mood: 'sleepy' }), /^You /);
    assert.match(receivedText(kind, 'Dudu', { mood: 'sleepy' }), /^Dudu /);
    const { title, body } = pushText(kind, 'Dudu', { mood: 'sleepy' });
    assert.ok(title.startsWith('Dudu'));
    assert.ok(body.length > 0, kind);
  }
});

test('status messages use mood labels and notes', () => {
  assert.equal(receivedText('status', 'Bubu', { mood: 'missyou' }), 'Bubu is now Missing you');
  assert.equal(pushText('status', 'Bubu', { mood: 'hungry', note: 'boba?' }).body, '“boba?”');
});
