// Праздничные логотипы (static/brand/season/*.png) и фоны открыток ко Дню матери. Запуск: node tools/seasons/render.js
const { chromium } = require('playwright'), path = require('path'), fs = require('fs');
const OUT = path.join(__dirname, '..', '..', 'static', 'brand', 'season');
(async () => { fs.mkdirSync(OUT, { recursive: true }); const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 512, height: 512 } });
  await p.goto('file://' + path.join(__dirname, 'logos.html')); await p.waitForTimeout(300);
  for (const k of ['ny', 'mom']) { await p.evaluate(k => draw(k), k); await p.waitForTimeout(80); await p.screenshot({ path: path.join(OUT, `logo-${k}.png`), omitBackground: true }); }
  if (fs.existsSync(path.join(__dirname, 'cards.html'))) {
    const c = await b.newPage({ viewport: { width: 1080, height: 1350 } });
    await c.goto('file://' + path.join(__dirname, 'cards.html')); await c.waitForTimeout(500);
    for (const k of await c.evaluate(() => Object.keys(CARDS))) { await c.evaluate(k => draw(k), k); await c.waitForTimeout(100); await c.screenshot({ path: path.join(OUT, `mom-${k}.png`) }); }
  }
  await b.close(); console.log('готово →', OUT); })();
