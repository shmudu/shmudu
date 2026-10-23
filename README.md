# Shmudu

A little web app for two: check in on each other's mood and send hugs, kisses, pokes and buns, starring Bubu (brown bear) and Dudu (white panda).

It's a web app you add to your iPhone's Home Screen, so it's free: no App Store, no Mac, no Apple Developer account.

- **Us**: both characters side by side, each showing your current mood. Tap Hug, Kiss, Poke, Snack or Thinking of you and your partner sees it right away, with a little animation.
- **My status**: pick a mood (Happy, Sleepy, Hungry, Missing you, Busy, Grumpy), what you're up to, and a short note.
- **Moments**: a running history of everything you've sent each other.
- **Notifications**: your partner's phone buzzes when you poke them, even with the app closed (iOS 16.4+, once it's on the Home Screen).

## Try it now (demo mode)

Until Firebase is set up, the app runs in **demo mode** with a pretend partner who replies to you. Everything stays on that one device.

```sh
npm start          # serves the app at http://localhost:3000
```

Add `?demo` to the URL to force demo mode even after Firebase is configured.

## Set it up for real (about 20 minutes, all free)

### 1. Firebase (stores your statuses and syncs them live)

1. Go to <https://console.firebase.google.com>, click **Create a project** (Google Analytics is not needed).
2. **Build → Authentication → Get started → Sign-in method → Anonymous → Enable.**
3. **Build → Firestore Database → Create database** (production mode, any location).
   Then open the **Rules** tab, replace everything with the contents of [`firestore.rules`](firestore.rules), and click **Publish**.
4. **Project settings (gear icon) → Your apps → Web (`</>`)**, register an app, and copy the `firebaseConfig` object into [`js/config.js`](js/config.js):

   ```js
   export const firebaseConfig = {
     apiKey: '...',
     authDomain: '...',
     projectId: '...',
     storageBucket: '...',
     messagingSenderId: '...',
     appId: '...',
   };
   ```

   These values are meant to be public; the security rules are what protect your data.

### 2. Notification keys (optional, but that's how pokes buzz the other phone)

1. Run `npx web-push generate-vapid-keys`. Put the **public** key in `js/config.js` as `vapidPublicKey`. Keep the private key for step 3.
2. In Firebase: **Project settings → Service accounts → Generate new private key**. This downloads a JSON file. **Never commit it.** It goes into Vercel only.

### 3. Host it on Vercel

1. Push this repo to GitHub, then at <https://vercel.com/new> import it (the free Hobby plan is fine). Framework preset: **Other**. No build command.
2. Under **Settings → Environment Variables**, add:

   | Name | Value |
   | --- | --- |
   | `FIREBASE_SERVICE_ACCOUNT` | the whole contents of the service-account JSON file |
   | `VAPID_PUBLIC_KEY` | public key from step 2 |
   | `VAPID_PRIVATE_KEY` | private key from step 2 |
   | `VAPID_SUBJECT` | `mailto:` plus your email, e.g. `mailto:you@example.com` |

3. Redeploy. You'll get a URL like `https://shmudu-yourname.vercel.app`.

### 4. Put it on both iPhones

On **each** phone:

1. Open the Vercel URL in **Safari**.
2. Tap **Share → Add to Home Screen → Add**.
3. Open **Shmudu from the Home Screen** (not from Safari) and pick your character and name.
4. One of you taps **Get a code**, the other enters it under **Partner's code**.
5. Tap **Turn on** when it asks about notifications.

> Do the setup inside the Home Screen app. On iPhone, the Home Screen app keeps its own storage separate from Safari, so pairing in a Safari tab won't carry over.

## Good to know

- **Your account is tied to the app on that phone.** Sign-in is anonymous, so if you delete the Home Screen app you'll need to pair again with a new code.
- **Unpair** only unpairs your phone. Pair again any time with a new code.
- **Costs:** Firebase's free Spark plan and Vercel's free Hobby plan are far more than two people will ever use.
- **Artwork:** the characters are original drawings in the style of Bubu & Dudu, not the official art. Fine for a private app for the two of you; don't publish it commercially.

## Project layout

```
index.html              the whole app shell
css/app.css             styles
js/app.js               UI, animations, navigation
js/characters.js        SVG drawings of Bubu and Dudu in every mood
js/messages.js          text for moments and notifications (shared with the server)
js/backend-demo.js      demo mode (localStorage + pretend partner)
js/backend-firebase.js  real mode (Firebase auth + Firestore, live updates)
js/push.js              web push permission and subscription
js/config.js            your Firebase config and VAPID public key
sw.js                   service worker: notifications + offline cache
api/notify.js           Vercel function that sends the push to your partner
firestore.rules         database security rules
scripts/make-icons.mjs  regenerates icons/ from the character drawings
tests/                  unit tests (npm test)
```
