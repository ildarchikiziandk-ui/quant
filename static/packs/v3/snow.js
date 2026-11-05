/* Снег на сайте (packs/v3/seasons.py): лёгкий холст поверх страницы, не мешает нажатиям.
   Выключается в настройках («Снег на сайте»), не идёт при «уменьшить движение» и на скрытой вкладке. */
(function () {
  try {
    if ((window.APP && APP.prefs && APP.prefs.season_snow === false) || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  } catch (e) { return; }
  const c = document.createElement('canvas'); c.className = 'nv-snow'; c.setAttribute('aria-hidden', 'true');
  c.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:950';
  document.body.appendChild(c);
  const x = c.getContext('2d'); let W, H, dpr, flakes = [], raf = 0, lastT = 0;
  const N = () => Math.round(Math.min(90, Math.max(30, innerWidth * innerHeight / 14000)));
  const mk = (top) => ({ x: Math.random() * W, y: top ? -10 : Math.random() * H, r: (Math.random() * 2.2 + 1) * dpr, v: (Math.random() * .5 + .35) * dpr, s: Math.random() * 6.28, w: Math.random() * .6 + .2 });
  function size() { dpr = Math.min(2, devicePixelRatio || 1); W = c.width = innerWidth * dpr; H = c.height = innerHeight * dpr; flakes = Array.from({ length: N() }, () => mk(false)); }
  function color() { return document.documentElement.dataset.theme === 'dark' ? 'rgba(255,255,255,.85)' : 'rgba(150,178,208,.85)'; }
  function tick(t) {
    const dt = Math.min(50, t - (lastT || t)) / 16.7; lastT = t; x.clearRect(0, 0, W, H); x.fillStyle = color();
    for (const f of flakes) { f.s += .02 * dt; f.y += f.v * dt; f.x += Math.sin(f.s) * f.w * dpr * dt * .5;
      if (f.y > H + 10) Object.assign(f, mk(true)); x.beginPath(); x.arc(f.x, f.y, f.r, 0, 6.283); x.fill(); }
    raf = requestAnimationFrame(tick);
  }
  size(); addEventListener('resize', size);
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else if (!raf) { lastT = 0; raf = requestAnimationFrame(tick); } });
  raf = requestAnimationFrame(tick);
})();
