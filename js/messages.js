// Shared text for interactions. Used by the app and by the push-notification function,
// so it must stay free of browser-only APIs.

export const ACTION_KINDS = ['hug', 'kiss', 'poke', 'snack', 'think'];
export const EVENT_KINDS = [...ACTION_KINDS, 'status'];

const MOOD_LABELS = {
  happy: 'Happy',
  sleepy: 'Sleepy',
  hungry: 'Hungry',
  missyou: 'Missing you',
  busy: 'Busy',
  grumpy: 'Grumpy',
};

export const moodLabel = (mood) => MOOD_LABELS[mood] ?? 'Happy';

/** Line shown in Moments for an event the current user sent. */
export function sentText(kind, partnerName, data = {}) {
  switch (kind) {
    case 'hug': return `You hugged ${partnerName}`;
    case 'kiss': return `You kissed ${partnerName}`;
    case 'poke': return `You poked ${partnerName}`;
    case 'snack': return `You sent ${partnerName} a bun`;
    case 'think': return `You thought of ${partnerName}`;
    case 'status': return `You are now ${moodLabel(data.mood)}`;
    default: return `You sent ${partnerName} something`;
  }
}

/** Line shown in Moments (and as a toast) for an event the partner sent. */
export function receivedText(kind, fromName, data = {}) {
  switch (kind) {
    case 'hug': return `${fromName} hugged you`;
    case 'kiss': return `${fromName} sent you a kiss`;
    case 'poke': return `${fromName} poked you!`;
    case 'snack': return `${fromName} sent you a bun`;
    case 'think': return `${fromName} is thinking of you`;
    case 'status': return `${fromName} is now ${moodLabel(data.mood)}`;
    default: return `${fromName} sent you something`;
  }
}

/** Title and body for the push notification the partner receives. */
export function pushText(kind, fromName, data = {}) {
  const title = receivedText(kind, fromName, data);
  const bodies = {
    hug: 'Open to hug back',
    kiss: 'Mwah! Send one back?',
    poke: 'Poke back?',
    snack: 'A warm bun, just for you',
    think: 'Send some love back',
  };
  const body = kind === 'status' ? (data.note ? `“${data.note}”` : 'Tap to see how they are') : bodies[kind] ?? '';
  return { title, body };
}

/** "just now", "5 min ago", "3 hr ago", "2 days ago". */
export function timeAgo(ms, now = Date.now()) {
  if (!ms) return 'a while ago';
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 45) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.round(h / 24);
  return d === 1 ? 'yesterday' : `${d} days ago`;
}
