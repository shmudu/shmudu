// Firebase backend: anonymous sign-in + Firestore, with real-time listeners.
//
// Data model (see firestore.rules):
//   users/{uid}                  { name, character, coupleId }
//   couples/{coupleId}           { members: [uid], code, profiles: {uid: {name, character}},
//                                  status: {uid: {mood, activity, note, updatedAt}},
//                                  counts: {hug, kiss, ...}, createdAt }
//   couples/{coupleId}/events/*  { from, kind, data, createdAt }
//   invites/{code}               { coupleId, createdBy, createdAt }
//   pushSubs/{uid}               { subs: [PushSubscriptionJSON] }   (read only by the server)

import { initializeApp } from 'firebase/app';
import { getAuth, onAuthStateChanged, signInAnonymously } from 'firebase/auth';
import {
  arrayUnion, collection, deleteDoc, doc, getDoc, getFirestore, increment, limit,
  onSnapshot, orderBy, query, serverTimestamp, setDoc, updateDoc, writeBatch,
} from 'firebase/firestore';
import { ACTION_KINDS } from './messages.js';
import { pushState, subscribe } from './push.js';

const millis = (ts) => (ts && typeof ts.toMillis === 'function' ? ts.toMillis() : Date.now());

export function createBackend({ firebaseConfig, vapidPublicKey }) {
  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  const db = getFirestore(app);

  let uid = null;
  let user = null; // users/{uid} data
  let couple = null; // couples/{id} data
  let events = [];
  let push = 'unconfigured';
  let listener = () => {};
  let unsubCouple = () => {};
  let unsubEvents = () => {};
  let watchedCoupleId = null;
  let coupleLoaded = false;
  let unsubUser = () => {};

  const coupleRef = () => doc(db, 'couples', user.coupleId);

  const snapshot = () => {
    const me = user?.name ? { uid, name: user.name, character: user.character } : null;
    const coupleId = couple ? user?.coupleId ?? null : null;
    const partnerUid = couple?.members?.find((m) => m !== uid) ?? null;
    const statuses = {};
    for (const [id, s] of Object.entries(couple?.status ?? {})) statuses[id] = { ...s, updatedAt: millis(s.updatedAt) };
    return {
      ready: uid !== null && user !== undefined && (!user.coupleId || coupleLoaded),
      mode: 'firebase',
      me,
      coupleId,
      waitingCode: couple && !partnerUid ? couple.code : null,
      partner: partnerUid ? { uid: partnerUid, ...(couple.profiles?.[partnerUid] ?? { name: 'Partner', character: 'dudu' }) } : null,
      statuses,
      counts: couple?.counts ?? {},
      events,
      push,
    };
  };

  const emit = () => listener(snapshot());

  const watchCouple = (coupleId) => {
    if (coupleId === watchedCoupleId) return;
    unsubCouple();
    unsubEvents();
    watchedCoupleId = coupleId;
    couple = null;
    events = [];
    coupleLoaded = !coupleId;
    if (!coupleId) return emit();
    const ref = doc(db, 'couples', coupleId);
    unsubCouple = onSnapshot(ref, (snap) => {
      couple = snap.exists() ? snap.data({ serverTimestamps: 'estimate' }) : null;
      coupleLoaded = true;
      emit();
    }, (err) => {
      console.warn('couple listener', err);
      coupleLoaded = true;
      emit();
    });
    const q = query(collection(ref, 'events'), orderBy('createdAt', 'desc'), limit(60));
    unsubEvents = onSnapshot(q, (snap) => {
      events = snap.docs.map((d) => {
        const e = d.data({ serverTimestamps: 'estimate' });
        return { id: d.id, from: e.from, kind: e.kind, data: e.data ?? {}, createdAt: millis(e.createdAt) };
      });
      emit();
    }, (err) => console.warn('events listener', err));
  };

  // Tell the server to push a notification to the partner. Best effort.
  const notify = async (eventId) => {
    try {
      const token = await auth.currentUser.getIdToken();
      await fetch('/api/notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ coupleId: user.coupleId, eventId }),
      });
    } catch (err) {
      console.warn('notify failed', err);
    }
  };

  const addEvent = async (kind, data, extraCoupleUpdate) => {
    const eventRef = doc(collection(coupleRef(), 'events'));
    const batch = writeBatch(db);
    batch.set(eventRef, { from: uid, kind, data, createdAt: serverTimestamp() });
    batch.update(coupleRef(), extraCoupleUpdate);
    await batch.commit();
    notify(eventRef.id);
  };

  return {
    mode: 'firebase',

    start(onChange) {
      listener = onChange;
      user = undefined;
      emit();
      pushState(vapidPublicKey).then((p) => { push = p; emit(); });
      onAuthStateChanged(auth, (u) => {
        if (!u) {
          signInAnonymously(auth).catch((err) => console.error('sign-in failed', err));
          return;
        }
        uid = u.uid;
        unsubUser();
        unsubUser = onSnapshot(doc(db, 'users', uid), (snap) => {
          user = snap.exists() ? snap.data() : {};
          watchCouple(user.coupleId ?? null);
          emit();
        }, (err) => console.error('user listener', err));
      });
    },

    async setProfile({ name, character }) {
      await setDoc(doc(db, 'users', uid), { name, character }, { merge: true });
      if (user?.coupleId && couple) {
        await updateDoc(coupleRef(), { [`profiles.${uid}`]: { name, character } });
      }
    },

    async createCouple() {
      let code;
      for (let i = 0; i < 5; i++) {
        code = String(Math.floor(100000 + Math.random() * 900000));
        if (!(await getDoc(doc(db, 'invites', code))).exists()) break;
      }
      const ref = doc(collection(db, 'couples'));
      await setDoc(ref, {
        members: [uid],
        code,
        profiles: { [uid]: { name: user.name, character: user.character } },
        status: { [uid]: { mood: 'happy', activity: 'Free to chat', note: '', updatedAt: serverTimestamp() } },
        counts: {},
        createdAt: serverTimestamp(),
      });
      await setDoc(doc(db, 'invites', code), { coupleId: ref.id, createdBy: uid, createdAt: serverTimestamp() });
      await setDoc(doc(db, 'users', uid), { coupleId: ref.id }, { merge: true });
      return code;
    },

    async joinCouple(code) {
      if (!/^\d{6}$/.test(code)) throw new Error('Codes are 6 digits');
      const invite = await getDoc(doc(db, 'invites', code));
      if (!invite.exists()) throw new Error('No one is waiting with that code');
      const { coupleId } = invite.data();
      try {
        await updateDoc(doc(db, 'couples', coupleId), {
          members: arrayUnion(uid),
          [`profiles.${uid}`]: { name: user.name, character: user.character },
          [`status.${uid}`]: { mood: 'happy', activity: 'Free to chat', note: '', updatedAt: serverTimestamp() },
        });
      } catch {
        throw new Error('That code has already been used');
      }
      await deleteDoc(doc(db, 'invites', code)).catch(() => {});
      await setDoc(doc(db, 'users', uid), { coupleId }, { merge: true });
    },

    async setStatus({ mood, activity, note }) {
      await addEvent('status', { mood, note }, {
        [`status.${uid}`]: { mood, activity, note, updatedAt: serverTimestamp() },
      });
    },

    async send(kind) {
      if (!ACTION_KINDS.includes(kind)) throw new Error(`Unknown action ${kind}`);
      await addEvent(kind, {}, { [`counts.${kind}`]: increment(1) });
    },

    async enablePush() {
      const sub = await subscribe(vapidPublicKey);
      await setDoc(doc(db, 'pushSubs', uid), { subs: arrayUnion(sub) }, { merge: true });
      push = 'granted';
      emit();
    },

    async leaveCouple() {
      await setDoc(doc(db, 'users', uid), { coupleId: null }, { merge: true });
    },
  };
}
