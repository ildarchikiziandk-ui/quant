// Праздничные логотипы: узор на кольце Q (как хохлома ко Дню народного единства). Запуск: node tools/seasons/rings.js
const { chromium } = require('playwright'), path = require('path'), fs = require('fs'), http = require('http');
const OUT = path.join(__dirname, '..', '..', 'static', 'brand', 'season'), KEYS = ['ny-1', 'ny-2', 'ny-3', 'mom-1', 'mom-2', 'mom-3'];
const srv = http.createServer((q, r) => { fs.readFile(path.join(__dirname, path.basename(q.url.split('?')[0])), (e, d) => { if (e) { r.statusCode = 404; return r.end(); } r.setHeader('Content-Type', q.url.endsWith('.png') ? 'image/png' : 'text/html; charset=utf-8'); r.end(d); }); });
srv.listen(0, async () => { fs.mkdirSync(OUT, { recursive: true }); const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 512, height: 512 } });
  await p.goto(`http://127.0.0.1:${srv.address().port}/rings.html`); await p.waitForTimeout(400);
  for (const k of (process.argv[2] ? process.argv[2].split(',') : KEYS)) { await p.evaluate(k => drawRing(k), k); await p.waitForTimeout(100); await p.screenshot({ path: path.join(OUT, `ring-${k}.png`), omitBackground: true }); }
  await b.close(); srv.close(); console.log('готово'); });
