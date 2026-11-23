#!/usr/bin/env node
/**
 * GPU-less ARM64 PRoot Headless Chromium UI audit template.
 *
 * Uses `/usr/bin/chromium-headless-shell` with Skia software rendering
 * (`--use-gl=disabled`) and strips Playwright's default `--enable-unsafe-swiftshader`
 * which crashes in GPU-less Linux containers.
 *
 * Setup (in a scratch/project dir):
 *   npm install playwright-core
 * Usage:
 *   node headless-ui-check.mjs http://127.0.0.1:8080/ ./out.png [width] [height] [dpr]
 */

import { chromium } from 'playwright-core';

const targetUrl = process.argv[2];
const outPng = process.argv[3] || './ui-check.png';
const width = Number(process.argv[4] || 390);
const height = Number(process.argv[5] || 844);
const dpr = Number(process.argv[6] || 2);

if (!targetUrl) {
  console.error('Usage: node headless-ui-check.mjs <url> [out.png] [width=390] [height=844] [dpr=2]');
  process.exit(1);
}

const executablePath = process.env.CHROMIUM_HEADLESS_BIN || '/usr/bin/chromium-headless-shell';

const browser = await chromium.launch({
  executablePath,
  headless: true,
  ignoreDefaultArgs: ['--enable-unsafe-swiftshader'],
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--use-gl=disabled',
    '--font-render-hinting=none',
  ],
});

try {
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: dpr,
  });
  const page = await context.newPage();

  const errors = [];
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });

  await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(300);

  const audit = await page.evaluate(() => {
    const overflows = [];
    const interactive = [];

    const isVisible = (el) => {
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
        return false;
      }
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1;
    };

    for (const el of document.querySelectorAll('button, a, [role="button"], .pill, .badge, .hud-item')) {
      if (!isVisible(el)) continue;
      const r = el.getBoundingClientRect();
      if (el.scrollWidth > el.clientWidth + 1) {
        overflows.push({
          tag: el.tagName.toLowerCase(),
          text: (el.innerText || '').trim().slice(0, 40),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
        });
      }
      interactive.push({
        label: (el.innerText || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 32),
        left: r.left,
        top: r.top,
        right: r.right,
        bottom: r.bottom,
      });
    }

    const overlaps = [];
    for (let i = 0; i < interactive.length; i++) {
      for (let j = i + 1; j < interactive.length; j++) {
        const a = interactive[i];
        const b = interactive[j];
        const dx = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const dy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (dx > 2 && dy > 2) {
          overlaps.push({ a: a.label, b: b.label, overlapPx: `${Math.round(dx)}x${Math.round(dy)}` });
        }
      }
    }

    return {
      docOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
      overflows,
      overlaps,
      checkedInteractiveCount: interactive.length,
    };
  });

  await page.screenshot({ path: outPng, fullPage: false });
  console.log(JSON.stringify({ url: targetUrl, viewport: `${width}x${height}@${dpr}x`, outPng, errors, audit }, null, 2));

  if (errors.length > 0) {
    process.exitCode = 2;
  }
} finally {
  await browser.close();
}
