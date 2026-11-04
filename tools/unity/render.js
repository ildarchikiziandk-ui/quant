// Рисует логотипы ко Дню народного единства: static/brand/unity/<slug>.png (512×512, прозрачный фон)
// и превью всех флагов в PNG (static/brand/unity/flags/<код>.png). Запуск: node tools/unity/render.js
// Список народов и цвета — packs/v3/unity_day.py (PEOPLES). Playwright в облаке уже установлен.
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), { execSync } = require('child_process');
const ROOT = path.join(__dirname, '..', '..'), OUT = path.join(ROOT, 'static', 'brand', 'unity');
const peoples = JSON.parse(execSync('python3 -c "import json,sys;sys.path.insert(0,\'.\');from packs.v3 import unity_day as u;print(json.dumps(u.peoples()))"', { cwd: ROOT, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim().split('\n').pop());
const srv = http.createServer((q, r) => { const f = path.join(__dirname, path.basename(q.url.split('?')[0]));
  fs.readFile(f, (e, d) => { if (e) { r.statusCode = 404; return r.end(); } r.setHeader('Content-Type', f.endsWith('.png') ? 'image/png' : 'text/html; charset=utf-8'); r.end(d); }); });
srv.listen(0, async () => {
  const port = srv.address().port, b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 512, height: 512 } });
  await p.goto(`http://127.0.0.1:${port}/page.html`); await p.waitForTimeout(300);
  for (const x of peoples) {
    await p.evaluate(x => window.draw(x), x); await p.waitForTimeout(80);
    await p.screenshot({ path: path.join(OUT, x.slug + '.png'), omitBackground: true });
  }
  // флаги — в PNG 120×80 (картинки, без чужого кода на странице)
  const f = await b.newPage({ viewport: { width: 120, height: 80 }, javaScriptEnabled: false });
  for (const code of [...new Set(peoples.map(x => x.flag).filter(Boolean))]) {
    const svg = fs.readFileSync(path.join(OUT, 'flags', code + '.svg'), 'utf8');
    await f.setContent(`<style>html,body{margin:0}svg{width:120px;height:80px;display:block}</style>${svg.replace('<svg ', '<svg preserveAspectRatio="none" ')}`);
    await f.screenshot({ path: path.join(OUT, 'flags', code + '.png') });
  }
  await b.close(); srv.close(); console.log('готово:', peoples.length, 'логотипов');
});
