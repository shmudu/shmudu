import { characterSVG, CHARACTERS, MOODS, MOOD_KEYS } from './characters.js';
import { firebaseConfig, vapidPublicKey } from './config.js';
import { receivedText, sentText, timeAgo } from './messages.js';
import { isStandalone } from './push.js';

const ACTIVITIES = ['Free to chat', 'At work', 'Eating', 'Napping', 'Gaming', 'On my way', 'Out with friends', 'Studying'];
const DOTS = { hug: '#E4577D', kiss: '#F28CA6', poke: '#F0A64B', snack: '#B98A5E', think: '#C9406A', status: '#7FA7E0' };
const TALLIES = [
  { kind: 'hug', label: 'Hugs', bg: '#FFD3DD' },
  { kind: 'kiss', label: 'Kisses', bg: '#FFE1EA' },
  { kind: 'poke', label: 'Pokes', bg: '#FFE7C7' },
  { kind: 'snack', label: 'Buns', bg: '#F3E3D2' },
  { kind: 'think', label: 'Thoughts', bg: '#EADDF6' },
];
const HEART = '<svg class="heart" viewBox="0 0 24 24"><path d="M12 21s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6-8 11-8 11z"/></svg>';
const BUN = '<svg viewBox="0 0 48 40"><path d="M4 30c0-12 9-22 20-22s20 10 20 22z" fill="#FFF3E2" stroke="#4B2A20" stroke-width="2.6" stroke-linejoin="round"/><path d="M16 29c2-5 2-11 0-15M24 29V9M32 29c-2-5-2-11 0-15" fill="none" stroke="#4B2A20" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="24" r="2.6" fill="#FBB9B9"/><circle cx="36" cy="24" r="2.6" fill="#FBB9B9"/></svg>';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const otherCharacter = (c) => (c === 'dudu' ? 'bubu' : 'dudu');

// ---------------------------------------------------------------------------
// State

let backend;
let snap = { ready: false };
const ui = {
  tab: 'home',
  obCharacter: null,
  meCharacter: null,
  draft: null, // { mood, activity, note } while editing status
  seenEvents: null, // Set of event ids already shown, null until first load
  drawn: {}, // cache of what is drawn in the scene so SVGs aren't rebuilt needlessly
  busy: false,
};

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Feedback

let toastTimer;
function toast(text) {
  const el = $('#toast');
  el.textContent = text;
  el.hidden = false;
  // Restart the pop animation.
  el.style.animation = 'none';
  void el.offsetWidth;
  el.style.animation = '';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
}

function restartClass(el, cls, ms) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), ms);
}

function spawn(html, cls, style, ms) {
  const wrap = document.createElement('div');
  wrap.innerHTML = html;
  const el = wrap.firstElementChild;
  if (cls) el.classList.add(...cls.split(' '));
  Object.assign(el.style, style);
  $('#fx').append(el);
  setTimeout(() => el.remove(), ms);
}

function hearts() {
  const spots = [[0, 0, ''], [-26, 14, 'light'], [28, 8, ''], [-6, 30, 'light']];
  spots.forEach(([dx, dy, light], i) => {
    spawn(HEART, light, {
      left: `calc(50% - 15px + ${dx}px)`,
      bottom: `${118 + dy}px`,
      animationDelay: `${i * 0.15}s`,
      opacity: '0',
    }, 2200);
  });
}

/** Plays the scene animation for an interaction. fromMe decides direction. */
function animate(kind, fromMe) {
  const scene = $('#scene');
  const target = fromMe ? $('#char-partner') : $('#char-me');
  const sender = fromMe ? $('#char-me') : $('#char-partner');
  switch (kind) {
    case 'hug':
      restartClass(scene, 'hug', 1500);
      hearts();
      break;
    case 'kiss':
      restartClass(sender, 'hop', 700);
      hearts();
      break;
    case 'poke':
      restartClass(target, 'wiggle', 800);
      break;
    case 'snack':
      spawn(BUN, `bun ${fromMe ? 'to-right' : 'to-left'}`, {}, 1400);
      setTimeout(() => restartClass(target, 'hop', 700), 1100);
      break;
    case 'think':
      hearts();
      break;
    case 'status':
      restartClass(sender, 'hop', 700);
      break;
  }
}

// ---------------------------------------------------------------------------
// Rendering

function showScreen(id) {
  for (const s of ['loading', 'onboard', 'pair', 'main']) $(`#${s}`).hidden = s !== id;
}

function render() {
  if (!snap.ready) return showScreen('loading');
  if (!snap.me) return renderOnboard();
  if (!snap.partner) return renderPair();
  renderMain();
}

function renderOnboard() {
  showScreen('onboard');
  for (const b of $$('[data-action="ob-character"]')) b.setAttribute('aria-pressed', String(b.dataset.arg === ui.obCharacter));
  const name = $('#ob-name');
  name.placeholder = ui.obCharacter ? CHARACTERS[ui.obCharacter].label : 'Your name';
}

function renderPair() {
  showScreen('pair');
  const mine = snap.me.character;
  const art = `${mine}:${snap.waitingCode ? 'waiting' : 'start'}`;
  if (ui.drawn.pair !== art) {
    $('#pair-art').innerHTML =
      `<div>${characterSVG(mine, 'happy')}</div><div>${characterSVG(otherCharacter(mine), snap.waitingCode ? 'sleepy' : 'missyou')}</div>`;
    ui.drawn.pair = art;
  }
  $('#pair-start').hidden = !!snap.waitingCode;
  $('#pair-waiting').hidden = !snap.waitingCode;
  $('#pair-code-show').textContent = snap.waitingCode ?? '';
  $('#pair-demo-note').hidden = snap.mode !== 'demo';
}

function statusOf(uid) {
  return snap.statuses?.[uid] ?? { mood: 'happy', activity: 'Free to chat', note: '', updatedAt: 0 };
}

function cardHTML(label, s) {
  const mood = MOODS[s.mood] ?? MOODS.happy;
  return `
    <span class="who">${esc(label)}</span>
    <span class="mood" style="background:${mood.tint}">${esc(mood.label)}</span>
    <span class="activity">${esc(s.activity)}</span>
    ${s.note ? `<span class="note">“${esc(s.note)}”</span>` : ''}
    <span class="when">Updated ${timeAgo(s.updatedAt)}</span>`;
}

function drawCharacter(slot, character, mood, label) {
  const key = `${character}:${mood}:${label}`;
  if (ui.drawn[slot] === key) return;
  $(`#${slot}`).innerHTML = characterSVG(character, mood, { label });
  ui.drawn[slot] = key;
}

function renderMain() {
  showScreen('main');
  const { me, partner } = snap;
  const myStatus = statusOf(me.uid);
  const theirStatus = statusOf(partner.uid);

  for (const section of $$('[data-tab]')) section.hidden = section.dataset.tab !== ui.tab;
  for (const b of $$('.tabbar button')) {
    if (b.dataset.arg === ui.tab) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  }

  // Home
  $('#home-title').textContent = `${me.name} & ${partner.name}`;
  $('#demo-pill').hidden = snap.mode !== 'demo';
  drawCharacter('char-me', me.character, myStatus.mood, `${me.name}, ${MOODS[myStatus.mood]?.label ?? ''}`);
  drawCharacter('char-partner', partner.character, theirStatus.mood, `${partner.name}, ${MOODS[theirStatus.mood]?.label ?? ''}`);
  $('#card-me').innerHTML = cardHTML(`You · ${me.name}`, myStatus);
  $('#card-partner').innerHTML = cardHTML(partner.name, theirStatus);
  const thinks = snap.counts?.think ?? 0;
  $('#think-label').textContent = thinks ? `Thinking of you · ${thinks}` : 'Thinking of you';
  renderPushBanner();

  // Status
  $('#status-title').textContent = `How are you, ${me.name}?`;
  if (!ui.draft) ui.draft = { mood: myStatus.mood, activity: myStatus.activity, note: myStatus.note ?? '' };
  $('#mood-grid').innerHTML = MOOD_KEYS.map((k) => `
    <button class="mood-btn" data-action="draft-mood" data-arg="${k}" aria-pressed="${ui.draft.mood === k}" style="--tint:${MOODS[k].tint}">
      <span class="face">${characterSVG(me.character, k, { faceOnly: true })}</span>${esc(MOODS[k].label)}
    </button>`).join('');
  const acts = ACTIVITIES.includes(ui.draft.activity) ? ACTIVITIES : [ui.draft.activity, ...ACTIVITIES];
  $('#activity-chips').innerHTML = acts.map((a) =>
    `<button class="chip" data-action="draft-activity" data-arg="${esc(a)}" aria-pressed="${ui.draft.activity === a}">${esc(a)}</button>`).join('');
  const note = $('#status-note');
  if (document.activeElement !== note) note.value = ui.draft.note;

  // Moments
  $('#tallies').innerHTML = TALLIES.map((t) =>
    `<div class="tally" style="background:${t.bg}"><b>${snap.counts?.[t.kind] ?? 0}</b><span>${t.label}</span></div>`).join('');
  const events = snap.events ?? [];
  $('#moments-list').innerHTML = events.length
    ? events.map((e) => {
        const text = e.from === me.uid ? sentText(e.kind, partner.name, e.data) : receivedText(e.kind, partner.name, e.data);
        return `<li><span class="dot" style="background:${DOTS[e.kind] ?? '#ccc'}"></span><span class="text">${esc(text)}</span><time>${timeAgo(e.createdAt)}</time></li>`;
      }).join('')
    : '<li class="empty">Nothing yet. Send a hug!</li>';

  // You
  const meName = $('#me-name');
  if (document.activeElement !== meName && !meName.dataset.dirty) meName.value = me.name;
  const meChar = ui.meCharacter ?? me.character;
  for (const b of $$('[data-action="me-character"]')) b.setAttribute('aria-pressed', String(b.dataset.arg === meChar));
  $('#me-pair-text').textContent = `You’re paired with ${partner.name}.`;
  $('#demo-reset').hidden = snap.mode !== 'demo';
  renderPushSettings();
}

const PUSH_TEXT = {
  unconfigured: 'Notifications aren’t set up for this app yet.',
  unsupported: 'This browser can’t show notifications from Shmudu.',
  'needs-install': 'To get pokes as notifications, add Shmudu to your Home Screen: tap Share, then “Add to Home Screen”, and open it from there.',
  default: 'Turn on notifications so you feel every poke and hug, even when the app is closed.',
  denied: 'Notifications are blocked. Turn them on in Settings › Notifications › Shmudu.',
  granted: 'Notifications are on.',
};

function renderPushBanner() {
  const state = snap.push;
  const show = (state === 'default' || state === 'needs-install') && storageGet('shmudu-push-dismissed') !== '1';
  $('#push-banner').hidden = !show;
  if (!show) return;
  $('#push-banner-text').textContent = PUSH_TEXT[state];
  $('#push-banner-btn').hidden = state !== 'default';
}

function renderPushSettings() {
  $('#me-push-text').textContent = PUSH_TEXT[snap.push] ?? '';
  $('#me-push-btn').hidden = snap.push !== 'default';
}

// ---------------------------------------------------------------------------
// Incoming events

function handleNewEvents() {
  const events = snap.events ?? [];
  if (!snap.partner) return;
  if (ui.seenEvents === null) {
    ui.seenEvents = new Set(events.map((e) => e.id));
    return;
  }
  const fresh = events.filter((e) => !ui.seenEvents.has(e.id));
  for (const e of fresh) ui.seenEvents.add(e.id);
  // Animate the newest incoming one; older ones just appear in Moments.
  const incoming = fresh.filter((e) => e.from === snap.partner.uid);
  if (incoming.length && ui.tab === 'home') {
    const e = incoming[0];
    animate(e.kind, false);
    toast(receivedText(e.kind, snap.partner.name, e.data));
  } else if (incoming.length) {
    toast(receivedText(incoming[0].kind, snap.partner.name, incoming[0].data));
  }
}

// ---------------------------------------------------------------------------
// Actions

async function run(fn) {
  if (ui.busy) return;
  ui.busy = true;
  try {
    await fn();
  } catch (err) {
    console.error(err);
    toast(err.message || 'Something went wrong');
  } finally {
    ui.busy = false;
  }
}

const actions = {
  'ob-character': (arg) => {
    ui.obCharacter = arg;
    render();
  },
  'ob-continue': () => run(async () => {
    if (!ui.obCharacter) throw new Error('Pick Bubu or Dudu first');
    const name = $('#ob-name').value.trim() || CHARACTERS[ui.obCharacter].label;
    await backend.setProfile({ name, character: ui.obCharacter });
  }),
  'pair-create': () => run(() => backend.createCouple()),
  'pair-join': () => run(() => backend.joinCouple($('#pair-code').value.trim())),
  tab: (arg) => {
    if (arg === 'status') ui.draft = null;
    ui.tab = arg;
    $('.content').scrollTop = 0;
    render();
  },
  send: (kind) => {
    animate(kind, true);
    toast(`Sent to ${snap.partner.name}`);
    backend.send(kind).catch((err) => {
      console.error(err);
      toast('Couldn’t send. Check your connection.');
    });
  },
  'draft-mood': (arg) => {
    ui.draft.mood = arg;
    render();
  },
  'draft-activity': (arg) => {
    ui.draft.activity = arg;
    render();
  },
  'status-save': () => run(async () => {
    const draft = { ...ui.draft, note: $('#status-note').value.trim() };
    await backend.setStatus(draft);
    ui.draft = null;
    ui.tab = 'home';
    $('.content').scrollTop = 0;
    render();
    animate('status', true);
    toast(`${snap.partner.name} can see your status`);
  }),
  'push-enable': () => run(async () => {
    await backend.enablePush();
    toast('Notifications on');
  }),
  'push-dismiss': () => {
    storageSet('shmudu-push-dismissed', '1');
    render();
  },
  'me-character': (arg) => {
    ui.meCharacter = arg;
    render();
  },
  'me-save': () => run(async () => {
    const name = $('#me-name').value.trim() || snap.me.name;
    await backend.setProfile({ name, character: ui.meCharacter ?? snap.me.character });
    delete $('#me-name').dataset.dirty;
    ui.meCharacter = null;
    toast('Saved');
  }),
  unpair: () => run(async () => {
    if (!confirm(`Unpair from ${snap.partner.name}? You can pair again with a new code.`)) return;
    await backend.leaveCouple();
    ui.seenEvents = null;
    ui.tab = 'home';
  }),
  'demo-reset': () => run(async () => {
    await backend.reset();
    ui.seenEvents = null;
    ui.tab = 'home';
    ui.obCharacter = null;
  }),
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  actions[el.dataset.action]?.(el.dataset.arg);
});

document.addEventListener('input', (e) => {
  if (e.target.id === 'status-note' && ui.draft) ui.draft.note = e.target.value;
  if (e.target.id === 'me-name') e.target.dataset.dirty = '1';
  if (e.target.id === 'pair-code') e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.target.id === 'ob-name') actions['ob-continue']();
  if (e.target.id === 'pair-code') actions['pair-join']();
});

// ---------------------------------------------------------------------------
// Boot

async function boot() {
  $('#loading-art').innerHTML = characterSVG('bubu', 'happy');
  for (const el of $$('[data-art]')) el.innerHTML = characterSVG(el.dataset.art, 'happy');

  const forceDemo = new URLSearchParams(location.search).has('demo');
  if (firebaseConfig && !forceDemo) {
    const { createBackend } = await import('./backend-firebase.js');
    backend = createBackend({ firebaseConfig, vapidPublicKey });
  } else {
    const { createBackend } = await import('./backend-demo.js');
    backend = createBackend();
  }

  backend.start((next) => {
    const wasPaired = !!snap.partner;
    snap = next;
    if (!snap.partner && wasPaired) ui.seenEvents = null;
    handleNewEvents();
    render();
  });

  // Refresh "5 min ago" labels.
  setInterval(() => { if (snap.partner) render(); }, 30_000);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch((err) => console.warn('service worker', err));
  }
  document.documentElement.classList.toggle('standalone', isStandalone());
}

boot();
