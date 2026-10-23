// Renders the app icons from the character drawings.
// Usage: node scripts/make-icons.mjs   (needs Playwright with a Chromium browser installed)

import { mkdir } from 'node:fs/promises';
import { characterSVG } from '../js/characters.js';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const html = `<!doctype html><html><body style="margin:0">
<div id="icon" style="width:512px;height:512px;background:#F9E1E3;display:flex;align-items:center;justify-content:center;overflow:hidden">
  <div style="width:268px;height:327px;margin-right:-40px;transform:rotate(-5deg) translateY(40px)">${characterSVG('bubu', 'happy')}</div>
  <div style="width:268px;height:327px;margin-left:-40px;transform:rotate(5deg) translateY(40px)">${characterSVG('dudu', 'happy')}</div>
</div>
<style>svg{width:100%;height:100%;display:block}</style>
</body></html>`;

await mkdir(new URL('../icons/', import.meta.url), { recursive: true });
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
for (const [file, size] of [['icon-512.png', 512], ['icon-192.png', 192], ['apple-touch-icon.png', 180]]) {
  const page = await browser.newPage({ viewport: { width: 512, height: 512 }, deviceScaleFactor: size / 512 });
  await page.setContent(html);
  await page.locator('#icon').screenshot({ path: new URL(`../icons/${file}`, import.meta.url).pathname });
  await page.close();
}
await browser.close();
console.log('Icons written to icons/');
