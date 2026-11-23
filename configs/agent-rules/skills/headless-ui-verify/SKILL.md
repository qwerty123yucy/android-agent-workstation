---
name: headless-ui-verify
description: >-
  Render web pages, Canvas apps, or mobile WebView UIs in Headless Chromium on a
  GPU-less Linux ARM64 PRoot container to audit DOM bounding-box overlaps, text
  truncation, missing font glyphs, and visual appearance via screenshots.
---

# Headless Chromium Visual & Layout Verification (GPU-less ARM64 PRoot)

Standard `/usr/bin/chromium` and Playwright's default `--enable-unsafe-swiftshader` flag crash in GPU-less Linux PRoot containers (`GPU process isn't usable / exit_code=256`). Always launch `/usr/bin/chromium-headless-shell` with Skia software rendering (`--use-gl=disabled`):

```js
const { chromium } = require('playwright-core');

const browser = await chromium.launch({
  executablePath: '/usr/bin/chromium-headless-shell',
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
```

- Install system packages: `apt install -y chromium-headless-shell fonts-wqy-zenhei`.
- Test real mobile target viewports (not desktop defaults), e.g., landscape `844x390` & compact `780x360`, portrait `390x844` & `360x780` at `deviceScaleFactor: 2`.
- Programmatically assert zero `pageerror` / `console.error`, check `el.scrollWidth > el.clientWidth + 1` on interactive pills/badges/buttons, and check pairwise `getBoundingClientRect()` intersections.
- Visually inspect rendered PNG screenshots to catch missing glyph tofu boxes (`□`), contrast defects, or cramped layout rhythm that geometry checks miss.
