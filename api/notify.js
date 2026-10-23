// Vercel serverless function: sends a push notification to your partner when you
// hug, poke, etc. The app calls it right after saving the event to Firestore.
//
// Environment variables (Vercel → Project → Settings → Environment Variables):
//   FIREBASE_SERVICE_ACCOUNT  the service-account JSON (Firebase → Project settings → Service accounts)
//   VAPID_PUBLIC_KEY          from `npx web-push generate-vapid-keys`
//   VAPID_PRIVATE_KEY         from the same command
//   VAPID_SUBJECT             mailto: address push services can contact, e.g. mailto:you@example.com

import { cert, getApps, initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import { FieldValue, getFirestore } from 'firebase-admin/firestore';
import webpush from 'web-push';
import { pushText } from '../js/messages.js';

function setup() {
  if (!getApps().length) {
    initializeApp({ credential: cert(JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT)) });
  }
  webpush.setVapidDetails(
    process.env.VAPID_SUBJECT || 'mailto:shmudu@example.com',
    process.env.VAPID_PUBLIC_KEY,
    process.env.VAPID_PRIVATE_KEY,
  );
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  if (!process.env.FIREBASE_SERVICE_ACCOUNT || !process.env.VAPID_PRIVATE_KEY) {
    return res.status(200).json({ sent: 0, skipped: 'push not configured' });
  }
  setup();

  const token = (req.headers.authorization || '').replace(/^Bearer /, '');
  let uid;
  try {
    uid = (await getAuth().verifyIdToken(token)).uid;
  } catch {
    return res.status(401).json({ error: 'Not signed in' });
  }

  const { coupleId, eventId } = req.body || {};
  if (typeof coupleId !== 'string' || typeof eventId !== 'string') {
    return res.status(400).json({ error: 'coupleId and eventId required' });
  }

  const db = getFirestore();
  const coupleRef = db.doc(`couples/${coupleId}`);
  const eventRef = coupleRef.collection('events').doc(eventId);

  // Only the sender may trigger a push, and only once per event.
  let couple;
  let event;
  try {
    await db.runTransaction(async (tx) => {
      const [c, e] = await Promise.all([tx.get(coupleRef), tx.get(eventRef)]);
      if (!c.exists || !e.exists) throw Object.assign(new Error('Not found'), { status: 404 });
      couple = c.data();
      event = e.data();
      if (!couple.members?.includes(uid) || event.from !== uid) throw Object.assign(new Error('Forbidden'), { status: 403 });
      if (event.notifiedAt) throw Object.assign(new Error('Already sent'), { status: 200 });
      tx.update(eventRef, { notifiedAt: FieldValue.serverTimestamp() });
    });
  } catch (err) {
    return res.status(err.status || 500).json({ sent: 0, error: err.message });
  }

  const partnerUid = couple.members.find((m) => m !== uid);
  if (!partnerUid) return res.status(200).json({ sent: 0 });

  const fromName = couple.profiles?.[uid]?.name || 'Your partner';
  const { title, body } = pushText(event.kind, fromName, event.data || {});
  const payload = JSON.stringify({ title, body, tag: `shmudu-${event.kind}` });

  const subsRef = db.doc(`pushSubs/${partnerUid}`);
  const subs = (await subsRef.get()).data()?.subs || [];
  const dead = [];
  let sent = 0;
  await Promise.all(subs.map(async (sub) => {
    try {
      await webpush.sendNotification(sub, payload, { TTL: 60 * 60 * 12, urgency: 'high' });
      sent++;
    } catch (err) {
      if (err.statusCode === 404 || err.statusCode === 410) dead.push(sub);
      else console.warn('push failed', err.statusCode, err.body);
    }
  }));
  if (dead.length) await subsRef.update({ subs: FieldValue.arrayRemove(...dead) });

  return res.status(200).json({ sent });
}
