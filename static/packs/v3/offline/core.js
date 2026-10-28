/* Nuvora: «Игры без интернета» — общий каркас. Во время игры к серверу не обращаемся вообще.
   Игра — файл offline/<id>.js, который вызывает OG.add({ id, title, icon, desc, modes, opts, start(ctx) }):
     modes — ['bot', 'duo'] (с ботом / вдвоём на одном телефоне) или ['solo'];
     opts  — переключатели над полем: [{ key, items: [[значение, подпись], …], bot: true — только в игре с ботом }];
     start(ctx) рисует игру в ctx.box. ctx: mode, opt, round (номер партии — для смены первого хода), names,
       status(html), over(html, кто победил: 0/1, -1 ничья), pass(кому, дальше) — экран «передайте телефон»,
       later(fn, мс) — таймер, который отменится при выходе из игры, key(fn) — клавиатура, swipe(el, fn) — смахивания.
   Логика игр и ботов не трогает DOM, поэтому её можно проверить в node (tests/offline_games_check.js).
   Игра по локальной сети потребует нативной части Android-приложения: браузер не умеет искать устройства в Wi‑Fi. */
(function (root) {
  'use strict';
  const OG = root.OG = root.OG || {};
  OG.games = [];
  OG.add = def => { OG.games.push(def); return def; };
  OG.rnd = n => Math.floor(Math.random() * n);
  OG.pick = a => a[OG.rnd(a.length)];
  OG.shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = OG.rnd(i + 1); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  OG.store = {
    get(k, d) { try { const v = localStorage.getItem('og:' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('og:' + k, JSON.stringify(v)); } catch (e) {} },
  };
  OG.esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  OG.icon = (n, c) => (root.ICON ? root.ICON(n, c || 'i in') : '');
  let data = null;  // словари с сервера (слова — не надписи, поэтому не в коде: их не тронет перевод)
  OG.data = () => {
    if (!data) { try { data = JSON.parse(document.getElementById('og-data').textContent); } catch (e) { data = {}; } }
    return data;
  };
  if (typeof document === 'undefined') return;  // node: только логика

  const MODES = { bot: ['bot', 'С ботом'], duo: ['users', 'Вдвоём'], solo: ['user', 'Один'] };
  const $ = (s, r = document) => r.querySelector(s);
  let cur = null;  // идущая игра: { def, ctx }

  function home() {
    const list = $('#og-list');
    const duel = OG.games.filter(g => !g.modes.includes('solo')), solo = OG.games.filter(g => g.modes.includes('solo'));
    const card = g => `<a class="og-card" href="#${g.id}"><span class="og-ic">${OG.icon(g.icon, 'i')}</span><b>${g.title}</b><span class="og-desc">${g.desc}</span>`
      + (g.modes.includes('solo') ? '' : `<span class="og-tags">${g.modes.map(m => `<i>${MODES[m][1]}</i>`).join('')}</span>`) + '</a>';
    list.innerHTML = `<div class="og-h">${OG.icon('users')} Вдвоём или с ботом</div><div class="og-grid">${duel.map(card).join('')}</div>`
      + `<div class="og-h">${OG.icon('user')} Для одного</div><div class="og-grid">${solo.map(card).join('')}</div>`;
  }

  function settings(def) {
    const s = OG.store.get('set:' + def.id, {});
    if (!def.modes.includes(s.mode)) s.mode = def.modes[0];
    s.opt = s.opt || {};
    (def.opts || []).forEach(o => { if (!o.items.some(i => i[0] === s.opt[o.key])) s.opt[o.key] = o.def || o.items[0][0]; });
    return s;
  }

  function open(def) {
    stop();
    const play = $('#og-play'), s = settings(def);
    $('#og-home').hidden = true; play.hidden = false;
    const chips = (key, items, val) => `<div class="og-seg" data-key="${key}">${items.map(([v, label]) => `<button type="button" data-v="${v}" class="${v === val ? 'on' : ''}">${label}</button>`).join('')}</div>`;
    const draw = () => {
      const opts = (def.opts || []).filter(o => !o.bot || s.mode === 'bot');
      play.innerHTML = `<div class="og-top"><a href="#" class="back-link" aria-label="Все игры">${OG.icon('back', 'i')}</a><span class="og-ic sm">${OG.icon(def.icon, 'i')}</span>`
        + `<b class="grow">${def.title}</b><button type="button" class="btn soft sm" data-og-new>${OG.icon('refresh')} Заново</button></div>`
        + `<div class="og-opts">${def.modes.length > 1 ? chips('mode', def.modes.map(m => [m, OG.icon(MODES[m][0]) + ' ' + MODES[m][1]]), s.mode) : ''}`
        + opts.map(o => chips(o.key, o.items, s.opt[o.key])).join('') + '</div>'
        + '<div class="og-score" hidden></div><div class="og-status" aria-live="polite"></div><div class="og-box"></div>';
      play.querySelectorAll('.og-seg').forEach(seg => seg.addEventListener('click', e => {
        const b = e.target.closest('[data-v]'); if (!b) return;
        if (seg.dataset.key === 'mode') s.mode = b.dataset.v; else s.opt[seg.dataset.key] = b.dataset.v;
        OG.store.set('set:' + def.id, s); round = 0; score = [0, 0]; draw();
      }));
      $('[data-og-new]', play).onclick = () => { round++; start(); };
      start();
    };
    let round = 0, score = [0, 0];
    const start = () => {
      stop();
      const box = $('.og-box', play), st = $('.og-status', play), sc = $('.og-score', play);
      box.innerHTML = ''; box.className = 'og-box og-g-' + def.id; st.innerHTML = '';
      const names = s.mode === 'bot' ? ['Вы', 'Бот'] : ['Игрок 1', 'Игрок 2'];
      const showScore = () => { sc.hidden = s.mode === 'solo' || !(score[0] + score[1]); sc.innerHTML = `${OG.esc(names[0])} <b>${score[0]}</b> : <b>${score[1]}</b> ${OG.esc(names[1])}`; };
      showScore();
      const timers = new Set(), offs = [];
      const ctx = {
        box, mode: s.mode, opt: Object.assign({}, s.opt), round, names, alive: true,
        status(html) { st.innerHTML = html; st.classList.remove('end'); },
        over(html, who) {
          if (!ctx.alive || ctx.ended) return;
          ctx.ended = true;
          if (who === 0 || who === 1) { score[who]++; showScore(); }
          st.innerHTML = `<span>${html}</span><button type="button" class="btn sm" data-og-again>Ещё раз</button>`; st.classList.add('end');
          $('[data-og-again]', st).onclick = () => { round++; start(); };
          if (who === 0 || (s.mode === 'duo' && who === 1)) confetti();
        },
        later(fn, ms) { const t = setTimeout(() => { timers.delete(t); if (ctx.alive) fn(); }, ms); timers.add(t); return t; },
        key(fn) { const h = e => { if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.target.closest('input,textarea')) fn(e); }; document.addEventListener('keydown', h); offs.push(() => document.removeEventListener('keydown', h)); },
        swipe(el, fn) {  // смахивание пальцем: fn('L' | 'R' | 'U' | 'D')
          let sx = 0, sy = 0;
          el.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }, { passive: true });
          el.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
          el.addEventListener('touchend', e => { const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy; if (Math.max(Math.abs(dx), Math.abs(dy)) >= 24) fn(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'R' : 'L') : (dy > 0 ? 'D' : 'U')); });
        },
        pass(who, next, note) {  // между ходами вдвоём: поле скрыто, пока телефон не у следующего игрока
          const ov = document.createElement('div'); ov.className = 'og-pass';
          ov.innerHTML = `${OG.icon('smartphone', 'i')}<b>Передайте телефон</b><span class="og-pass-who">${OG.esc(who)}</span>${note ? `<span class="small muted">${note}</span>` : ''}<button type="button" class="btn">Показать поле</button>`;
          box.appendChild(ov); box.classList.add('hide'); st.innerHTML = '';  // и подсказку прошлого хода прячем
          $('button', ov).onclick = () => { ov.remove(); box.classList.remove('hide'); if (ctx.alive) next(); };
        },
        stop() { ctx.alive = false; timers.forEach(clearTimeout); offs.forEach(f => f()); if (ctx.cleanup) ctx.cleanup(); },
      };
      cur = { def, ctx };
      try { def.start(ctx); } catch (e) { st.textContent = 'Не удалось запустить игру'; console.error(e); }
    };
    draw();
    scrollTo(0, 0);
  }

  function stop() { if (cur) { cur.ctx.stop(); cur = null; } }

  function route() {
    const id = decodeURIComponent(location.hash.slice(1)), def = OG.games.find(g => g.id === id);
    if (def) { open(def); return; }
    stop();
    $('#og-play').hidden = true; $('#og-play').innerHTML = ''; $('#og-home').hidden = false;
  }

  function confetti() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const layer = document.createElement('div'); layer.className = 'og-fx';
    const colors = ['#1f6fb8', '#c2552f', '#c98a1b', '#3c9a5f', '#e0475a'];
    for (let i = 0; i < 36; i++) {
      const p = document.createElement('i');
      p.style.left = Math.random() * 100 + '%'; p.style.background = colors[i % colors.length];
      p.style.animationDelay = Math.random() * .6 + 's'; p.style.animationDuration = 1.6 + Math.random() * 1.2 + 's';
      layer.appendChild(p);
    }
    document.body.appendChild(layer); setTimeout(() => layer.remove(), 3600);
  }
  OG.confetti = confetti;

  document.addEventListener('DOMContentLoaded', () => {
    if (!$('#og-app')) return;
    // сервис-воркер кладёт раздел в кэш; app.js регистрирует его только после входа, а играть можно и без аккаунта
    if ('serviceWorker' in navigator && !(root.APP && root.APP.user)) navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
    home();
    addEventListener('hashchange', route);
    route();
  });
})(typeof window !== 'undefined' ? window : globalThis);
