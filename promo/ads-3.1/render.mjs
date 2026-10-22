import { chromium } from '/opt/node-tools/node_modules/playwright/index.mjs';
import { spawn } from 'child_process';
const [mode, ad, out, extra] = process.argv.slice(2);
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await (await b.newContext({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 2 })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(`http://127.0.0.1:8811/ads.html?ad=${ad}`); await p.waitForFunction('window.READY');
if (mode === 'shots') {
  for (const t of extra.split(',')) { await p.evaluate(t => seek(t), +t); await p.screenshot({ path: `${out}-${t}.png` }); }
} else {
  const fps = 30, N = 14 * fps;
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', '30', '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let f = 0; f < N; f++) { await p.evaluate(t => seek(t), f / fps); const buf = await p.screenshot({ type: 'jpeg', quality: 93 }); if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r)); }
  ff.stdin.end(); await new Promise(r => ff.on('close', r));
}
console.log(errs.length ? 'ERR ' + errs.join(' | ') : 'ok', ad);
await b.close();
