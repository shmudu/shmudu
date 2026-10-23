// Demo backend: everything lives in localStorage and the partner is simulated,
// so the app can be tried before Firebase is set up.

const KEY = 'shmudu-demo-v1';
const ME = 'me';
const PARTNER = 'partner';

const REPLIES = { hug: 'hug', kiss: 'kiss', poke: 'poke', snack: 'think', think: 'kiss' };

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) ?? null;
  } catch {
    return null;
  }
}

function save(db) {
  try {
    localStorage.setItem(KEY, JSON.stringify(db));
  } catch {
    // Storage unavailable (private mode); the demo still works for this visit.
  }
}

function fresh() {
  return { profile: null, paired: false, waitingCode: null, statuses: {}, counts: {}, events: [] };
}

export function createBackend() {
  let db = load() ?? fresh();
  let listener = () => {};
  const timers = new Set();

  const later = (ms, fn) => {
    const t = setTimeout(() => {
      timers.delete(t);
      fn();
    }, ms);
    timers.add(t);
  };

  const partnerProfile = () => {
    const character = db.profile?.character === 'dudu' ? 'bubu' : 'dudu';
    return { uid: PARTNER, name: character === 'dudu' ? 'Dudu' : 'Bubu', character };
  };

  const snapshot = () => ({
    ready: true,
    mode: 'demo',
    me: db.profile ? { uid: ME, ...db.profile } : null,
    coupleId: db.paired ? 'demo' : null,
    waitingCode: db.waitingCode,
    partner: db.paired ? partnerProfile() : null,
    statuses: db.statuses,
    counts: db.counts,
    events: db.events,
    push: 'unconfigured',
  });

  const commit = () => {
    save(db);
    listener(snapshot());
  };

  const addEvent = (from, kind, data = {}) => {
    db.events = [{ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, from, kind, data, createdAt: Date.now() }, ...db.events].slice(0, 60);
    if (kind !== 'status') db.counts = { ...db.counts, [kind]: (db.counts[kind] ?? 0) + 1 };
  };

  const pairWithDemoPartner = () => {
    db.paired = true;
    db.waitingCode = null;
    db.statuses[PARTNER] = { mood: 'sleepy', activity: 'Napping', note: '5 more minutes…', updatedAt: Date.now() - 8 * 60 * 1000 };
    addEvent(PARTNER, 'kiss');
    commit();
  };

  return {
    mode: 'demo',

    start(onChange) {
      listener = onChange;
      commit();
    },

    async setProfile({ name, character }) {
      db.profile = { name, character };
      if (!db.statuses[ME]) db.statuses[ME] = { mood: 'happy', activity: 'Free to chat', note: '', updatedAt: Date.now() };
      commit();
    },

    async createCouple() {
      db.waitingCode = String(Math.floor(100000 + Math.random() * 900000));
      commit();
      // Pretend the partner enters the code a few seconds later.
      later(4000, pairWithDemoPartner);
      return db.waitingCode;
    },

    async joinCouple(code) {
      if (!/^\d{6}$/.test(code)) throw new Error('Codes are 6 digits');
      pairWithDemoPartner();
    },

    async setStatus(status) {
      db.statuses[ME] = { ...status, updatedAt: Date.now() };
      addEvent(ME, 'status', { mood: status.mood, note: status.note });
      commit();
    },

    async send(kind) {
      addEvent(ME, kind);
      commit();
      const reply = REPLIES[kind];
      if (reply) {
        later(2200, () => {
          addEvent(PARTNER, reply);
          commit();
        });
      }
    },

    async enablePush() {
      throw new Error('Notifications work once Firebase is connected');
    },

    async leaveCouple() {
      timers.forEach(clearTimeout);
      timers.clear();
      db = { ...fresh(), profile: db.profile, statuses: { [ME]: db.statuses[ME] } };
      commit();
    },

    async reset() {
      timers.forEach(clearTimeout);
      timers.clear();
      db = fresh();
      commit();
    },
  };
}
