/* Снег на сайте (packs/v3/seasons.py): лёгкий холст поверх страницы, не мешает нажатиям.
   Выключается в настройках («Снег на сайте»), не идёт при «уменьшить движение» и на скрытой вкладке.
   Оптимизация (7.11.2026): рисуем в обычном разрешении (не ×2 — снежинкам не нужна чёткость), 30 кадров в секунду,
   во время прокрутки и касаний кадры реже, при появлении/скрытии адресной строки снег не пересоздаётся. */
(function () {
  try {
    if ((window.APP && APP.prefs && APP.prefs.season_snow === false) || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  } catch (e) { return; }
  const c = document.createElement('canvas'); c.className = 'nv-snow'; c.setAttribute('aria-hidden', 'true');
  c.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:950;contain:strict';
  document.body.appendChild(c);
  const x = c.getContext('2d', { alpha: true, desynchronized: true });
  let W = 0, H = 0, flakes = [], raf = 0, last = 0, busyUntil = 0, col = '';
  const N = () => Math.round(Math.min(60, Math.max(24, innerWidth * innerHeight / 20000)));
  const mk = top => ({ x: Math.random() * W, y: top ? -6 : Math.random() * H, r: Math.random() * 1.8 + 1, v: Math.random() * .45 + .35, s: Math.random() * 6.28, w: Math.random() * .5 + .2 });
  function size() {
    const nw = innerWidth, nh = innerHeight;
    if (nw === W && Math.abs(nh - H) < 160 && flakes.length) { H = c.height = nh; return; }  // адресная строка — только высота
    W = c.width = nw; H = c.height = nh; flakes = Array.from({ length: N() }, () => mk(false));
  }
  const color = () => (col = document.documentElement.dataset.theme === 'dark' ? 'rgba(255,255,255,.8)' : 'rgba(150,178,208,.85)');
  function tick(t) {
    raf = requestAnimationFrame(tick);
    const gap = t < busyUntil ? 66 : 33;  // 30 кадров, а пока листают — 15: прокрутке достаётся весь телефон
    if (t - last < gap) return;
    const dt = Math.min(4, (t - (last || t)) / 16.7); last = t;
    x.clearRect(0, 0, W, H); x.fillStyle = col; x.beginPath();
    for (const f of flakes) {
      f.s += .02 * dt; f.y += f.v * dt; f.x += Math.sin(f.s) * f.w * dt * .5;
      if (f.y > H + 6) Object.assign(f, mk(true));
      x.moveTo(f.x + f.r, f.y); x.arc(f.x, f.y, f.r, 0, 6.283);
    }
    x.fill();  // все снежинки — одной командой рисования
  }
  let rs = 0; size(); color();
  addEventListener('resize', () => { clearTimeout(rs); rs = setTimeout(size, 150); });
  const busy = () => { busyUntil = performance.now() + 300; };
  addEventListener('scroll', busy, { passive: true, capture: true }); addEventListener('touchmove', busy, { passive: true });
  new MutationObserver(color).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else if (!raf) { last = 0; raf = requestAnimationFrame(tick); } });
  raf = requestAnimationFrame(tick);
})();
