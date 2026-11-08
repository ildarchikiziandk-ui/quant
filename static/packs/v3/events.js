/* Ивенты (packs/v3/events.py): заставка раз за запуск, подарки, адвент, блины, валентинки, снежинки, салют, кит 1 апреля. */
(function () {
  const B = document.body, ON = (B.dataset.ev || '').split(' ').filter(Boolean);
  const has = k => ON.includes(k);
  const ss = (k, v) => { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return '1'; } };
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
  const toast = m => (window.App && window.App.toast ? window.App.toast(m) : alert(m));
  const post = (u, body) => fetch(u, { method: 'POST', credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
    .then(r => r.json().catch(() => ({ ok: false, error: 'Ошибка' })));

  // заставка
  const sp = document.getElementById('ev-splash');
  if (sp && !ss('nv_ev_' + sp.dataset.key) && !document.getElementById('ssplash')?.offsetParent) {
    ss('nv_ev_' + sp.dataset.key, '1'); sp.hidden = false; requestAnimationFrame(() => sp.classList.add('show'));
    const close = () => { sp.classList.remove('show'); setTimeout(() => sp.remove(), 300); };
    sp.addEventListener('click', e => { if (e.target === sp) close(); }); setTimeout(close, 5000);
    if (['bday', 'owner_bday', 'summer1'].includes(sp.dataset.key)) confetti();
  }

  // кнопки «забрать подарок»
  document.addEventListener('click', e => {
    const g = e.target.closest('[data-ev-gift]');
    if (g) { g.disabled = true; post('/prazdniki/' + g.dataset.evGift + '/gift').then(r => { toast(r.ok ? '🎁 ' + r.text : r.error); if (r.ok) { g.textContent = '✓ Получено'; confetti(); } else g.disabled = false; }); }
    const a = e.target.closest('[data-adv-open]');
    if (a) { a.disabled = true; post('/advent/open').then(r => { if (r.ok) { a.classList.remove('today'); a.classList.add('got'); a.insertAdjacentHTML('beforeend', `<span class="adv-p">${r.text}</span>`); toast('🎁 ' + r.text); confetti(); } else { toast(r.error); a.disabled = false; } }); }
    const bl = e.target.closest('[data-ev-blin]');
    if (bl) { bl.disabled = true; post('/maslenitsa/blin').then(r => { toast(r.ok ? '🥞 ' + r.text : r.error); if (r.ok) setTimeout(() => location.reload(), 900); else bl.disabled = false; }); }
  });

  // валентинки
  const vf = document.getElementById('val-form');
  if (vf) {
    const img = document.getElementById('val-prev'); let tm;
    const upd = () => { clearTimeout(tm); tm = setTimeout(() => { img.src = '/valentine/preview.png?' + new URLSearchParams({ c: vf.card.value, t: vf.text.value }); }, 350); };
    vf.addEventListener('input', upd); vf.addEventListener('change', upd); upd();
    document.getElementById('val-send').onclick = () => {
      if (!vf.to.value.trim()) { vf.to.focus(); return; }
      post('/valentine/send', { to: vf.to.value.trim(), card: vf.card.value, text: vf.text.value, anon: vf.anon.checked ? 1 : 0 })
        .then(r => { toast(r.ok ? '💌 Валентинка отправлена!' : r.error); if (r.ok) { vf.to.value = ''; confetti(['#d6336c', '#ff8fab', '#fff']); } });
    };
  }

  // «Первый снег»: золотые снежинки — поймай 10
  if (has('snow1') && B.dataset.me) fetch('/prazdniki/state.json', { credentials: 'same-origin' }).then(r => r.json()).then(st => {
    if (!st.snow) return;
    const key = 'nv_snow1_' + new Date().getFullYear(); let n = +(ls(key) || 0), live = 0;
    const spawn = () => {
      if (n >= 10 || live >= 2 || document.hidden) return;
      const f = document.createElement('div'); f.className = 'ev-flake'; f.textContent = '❄'; live++;
      const x = 10 + Math.random() * (innerWidth - 70), dur = 9000 + Math.random() * 5000, t0 = performance.now(), sway = 20 + Math.random() * 30;
      f.style.left = x + 'px'; document.body.appendChild(f);
      const step = t => { const p = (t - t0) / dur; if (p >= 1 || f.classList.contains('caught')) { if (!f.classList.contains('caught')) { f.remove(); live--; } return; }
        f.style.transform = `translate(${Math.sin(p * 9) * sway}px, ${p * (innerHeight + 120)}px) rotate(${p * 360}deg)`; requestAnimationFrame(step); };
      requestAnimationFrame(step);
      f.addEventListener('pointerdown', () => {
        f.classList.add('caught'); live--; setTimeout(() => f.remove(), 400); n++; ls(key, n);
        if (n >= 10) post('/prazdniki/snow1/catch').then(r => { toast(r.ok ? '❄ 10 снежинок! ' + r.text : r.error); if (r.ok) confetti(['#f0b400', '#fff', '#9fd3ff']); });
        else toast(`❄ Снежинок: ${n} из 10`);
      });
    };
    setInterval(spawn, 4000); setTimeout(spawn, 1200);
  });

  // Новый год: салют 1 января
  if (has('nynight')) { const d = new Date(); if (d.getMonth() === 0 && !ss('nv_fw')) { ss('nv_fw', '1'); fireworks(); } }

  // 1 апреля: кит плавает по экрану
  if (has('apr1')) { const w = document.createElement('img'); w.src = '/static/brand/logo-mark-warm.png'; w.className = 'ev-whale'; w.alt = ''; document.body.appendChild(w);
    let t0 = performance.now(); const swim = t => { const p = ((t - t0) / 16000) % 1, x = -80 + p * (innerWidth + 160), y = innerHeight * .35 + Math.sin(p * 12) * 40;
      w.style.transform = `translate(${x}px, ${y}px) scaleX(-1)`; requestAnimationFrame(swim); }; requestAnimationFrame(swim); }

  function canvas() { const c = document.createElement('canvas'); c.className = 'ev-canvas'; c.width = innerWidth; c.height = innerHeight; document.body.appendChild(c); return c; }
  function confetti(cols) {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const c = canvas(), x = c.getContext('2d'), C = cols || ['#b5562f', '#f0c24a', '#2f7a4a', '#1f6fb8', '#d6336c'];
    const P = Array.from({ length: 90 }, () => ({ x: innerWidth / 2, y: innerHeight * .4, vx: (Math.random() - .5) * 14, vy: -Math.random() * 14 - 4, r: Math.random() * 6, c: C[Math.random() * C.length | 0], a: Math.random() * 6 }));
    let t = 0; const f = () => { x.clearRect(0, 0, c.width, c.height); P.forEach(p => { p.vy += .45; p.x += p.vx; p.y += p.vy; p.a += .2; x.save(); x.translate(p.x, p.y); x.rotate(p.a); x.fillStyle = p.c; x.fillRect(-4, -2, 8, 4 + p.r); x.restore(); });
      if (++t < 110) requestAnimationFrame(f); else c.remove(); }; f();
  }
  function fireworks() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const c = canvas(), x = c.getContext('2d'), P = []; let t = 0;
    const boom = () => { const cx = innerWidth * (.2 + Math.random() * .6), cy = innerHeight * (.15 + Math.random() * .35), col = `hsl(${Math.random() * 360},90%,60%)`;
      for (let i = 0; i < 60; i++) { const a = i / 60 * Math.PI * 2, s = 2 + Math.random() * 4; P.push({ x: cx, y: cy, vx: Math.cos(a) * s, vy: Math.sin(a) * s, l: 60, c: col }); } };
    const f = () => { if (t % 25 === 0 && t < 200) boom(); x.fillStyle = 'rgba(0,0,0,0.12)'; x.clearRect(0, 0, c.width, c.height);
      for (let i = P.length - 1; i >= 0; i--) { const p = P[i]; p.vy += .05; p.x += p.vx; p.y += p.vy; p.l--; x.globalAlpha = Math.max(0, p.l / 60); x.fillStyle = p.c; x.fillRect(p.x, p.y, 3, 3); if (p.l <= 0) P.splice(i, 1); }
      x.globalAlpha = 1; if (++t < 280) requestAnimationFrame(f); else c.remove(); }; f();
  }
})();
