/* Nuvora 3.x: опросы и игры в чатах, эффекты, папки, сундук, капсула,
   настроение, капсула, «Словечко», 2048, резервные коды, группировка уведомлений, поиск по помощи. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const A = window.App, IC = (n, c) => (window.ICON ? ICON(n, c || 'i in') : '');
  const on = (sel, fn) => document.addEventListener('click', e => { const el = e.target.closest(sel); if (el) fn(el, e); });
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
                  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
  const formData = f => Object.fromEntries(new FormData(f).entries());
  const plural = (n, a, b, c) => { const m10 = n % 10, m100 = n % 100; return n + ' ' + (m10 === 1 && m100 !== 11 ? a : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20) ? b : c); };

  // ================================================================ карточки в чате
  async function refreshCard(el) {
    const msg = el.closest('.msg'); if (!msg) return;
    try {
      const r = await A.get('/messages/fragment/' + msg.dataset.id);
      const t = document.createElement('div'); t.innerHTML = r.html;
      const fresh = t.firstElementChild;
      const was = msg.querySelector('.v3-card'), now = fresh && fresh.querySelector('.v3-card');
      if (was && now && was.innerHTML === now.innerHTML) return;  // ничего не изменилось — не перерисовываем
      if (fresh) { delete msg.dataset.v3fx; msg.replaceWith(fresh); fresh.dataset.v3fx = '1'; }
    } catch (e) {}
  }
  on('[data-v3-vote]', async b => { try { await A.api(`/v3/poll/${b.dataset.v3Vote}/vote`, { option: b.dataset.opt }); refreshCard(b); } catch (e) {} });
  on('[data-v3-close]', async b => { if (!confirm('Закрыть опрос? Голосовать больше будет нельзя.')) return; try { await A.api(`/v3/poll/${b.dataset.v3Close}/close`); refreshCard(b); } catch (e) {} });
  on('[data-v3-move]', async b => { b.disabled = true; try { await A.api(`/v3/ttt/${b.dataset.v3Move}/move`, { cell: b.dataset.cell }); refreshCard(b); } catch (e) { b.disabled = false; } });
  on('[data-v3-rematch]', async b => { try { await A.api(`/v3/ttt/${b.dataset.v3Rematch}/rematch`); window.poll?.(); } catch (e) {} });
  // живые карточки (открытый опрос, идущая партия) обновляются сами, пока чат открыт
  setInterval(() => { if (document.hidden) return; $$('.v3-live').slice(-6).forEach(c => { const r = c.getBoundingClientRect(); if (r.bottom > 0 && r.top < innerHeight) refreshCard(c); }); }, 3500);

  // игры: «Камень, ножницы, бумага», «Кости», «Четыре в ряд», «Виселица», «Морской бой»
  on('[data-v3-gmove]', async b => {
    const card = b.closest('.v3-card'); card?.querySelectorAll('[data-v3-gmove]').forEach(x => x.disabled = true);
    try { await A.api(`/v3/game/${b.dataset.v3Gmove}/move`, { v: b.dataset.v }); } catch (e) {}
    refreshCard(b);
  });
  const askWord = () => new Promise(res => {
    const md = A.modal('Загадайте слово', `<p class="small muted mb">Одно слово русскими буквами, 3–14 букв. Соперник будет угадывать его по буквам, у него 6 ошибок.</p>
      <input id="v3-hw" type="password" maxlength="14" autocomplete="off" placeholder="Например, черепаха"><label class="check mt"><input type="checkbox" id="v3-hs"><span>Показать слово</span></label><button class="btn block mt" id="v3-hgo">Загадать</button>`);
    const inp = $('#v3-hw', md); inp.focus();
    $('#v3-hs', md).onchange = e => { inp.type = e.target.checked ? 'text' : 'password'; };
    const go = () => { const w = inp.value.trim(); if (!w) return; md.classList.remove('open'); res(w); };
    $('#v3-hgo', md).onclick = go; inp.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); go(); } };
  });
  on('[data-v3-grematch]', async b => {
    const body = {};
    if (b.dataset.hang) body.word = await askWord();
    try { await A.api(`/v3/game/${b.dataset.v3Grematch}/rematch`, body); window.poll?.(); } catch (e) {}
  });
  const GAMES = [['ttt', 'grid', 'Крестики-нолики', 'по очереди, три в ряд'], ['c4', 'layers', 'Четыре в ряд', 'фишки падают вниз, нужно четыре подряд'],
    ['rps', 'wave', 'Камень, ножницы, бумага', 'до двух побед'], ['dice', 'dice', 'Кости', 'у кого больше на двух кубиках'],
    ['hang', 'type', 'Виселица', 'вы загадываете слово, друг угадывает'], ['sea', 'target', 'Морской бой', 'поле 8×8, флот расставится сам']];
  // «+» в переписке: опрос или игра
  on('[data-v3-attach]', b => {
    const u = b.dataset.v3Attach;
    const md = A.modal('Отправить в чат', `<div class="row mb" style="gap:8px"><button class="btn soft grow" data-k="poll">${IC('poll')} Опрос</button><button class="btn soft grow" data-k="gift">${IC('gift')} Подарок</button></div><div class="tiny faint mb">Игры</div>`
      + `<div class="v3-gamepick">${GAMES.map(g => `<button type="button" data-k="${g[0]}">${IC(g[1])}<b>${g[2]}</b><span>${g[3]}</span></button>`).join('')}</div>`);
    $('[data-k=poll]', md).onclick = () => pollForm(u);
    $('[data-k=gift]', md).onclick = () => giftForm(u);
    GAMES.forEach(([k]) => { $(`[data-k=${k}]`, md).onclick = async () => {
      md.classList.remove('open');
      try {
        if (k === 'ttt') await A.api(`/v3/chat/${encodeURIComponent(u)}/ttt`);
        else await A.api(`/v3/chat/${encodeURIComponent(u)}/game`, k === 'hang' ? { kind: k, word: await askWord() } : { kind: k });
        await window.poll?.();
      } catch (e) {}
    }; });
  });
  async function giftForm(u) {
    let r; try { r = await A.get('/v3/gifts'); } catch (e) { return; }
    const md = A.modal('Подарок', `<div class="small muted mb">У вас ${r.balance} искр. Подарок появится в переписке и в профиле получателя.</div>
      <div class="v3-giftpick">${r.gifts.map(g => `<button type="button" data-g="${g.code}"${g.plus && !r.plus ? ' disabled title="Только с Nuvora+"' : ''}><img src="/static/gifts/${g.code}.svg" alt=""><b>${g.name}</b><span>${g.price} искр${g.plus ? ' · Plus' : ''}</span></button>`).join('')}</div>
      <input id="v3-gmsg" maxlength="140" placeholder="Подпись (необязательно)" class="mt"><button class="btn block mt" id="v3-ggo" disabled>Подарить</button>`);
    let pick = '';
    $$('[data-g]', md).forEach(b => b.onclick = () => { $$('[data-g]', md).forEach(x => x.classList.remove('on')); b.classList.add('on'); pick = b.dataset.g; $('#v3-ggo', md).disabled = false; });
    $('#v3-ggo', md).onclick = async () => {
      try { await A.api(`/gifts/${encodeURIComponent(u)}/send`, { gift: pick, message: $('#v3-gmsg', md).value }); md.classList.remove('open'); A.toast('Подарок отправлен'); play('confetti'); await window.poll?.(); } catch (e) {}
    };
  }
  function pollForm(u) {
    const md = A.modal('Новый опрос', `<input id="v3-pq" maxlength="200" placeholder="Вопрос"><div id="v3-po" class="mt"></div>
      <button type="button" class="btn ghost sm" id="v3-padd">${IC('plus')} Вариант</button>
      <label class="check mt"><input type="checkbox" id="v3-pm"><span>Можно выбрать несколько</span></label><button class="btn block mt" id="v3-pgo">Отправить</button>`);
    const box = $('#v3-po', md);
    const add = () => { if (box.children.length >= 10) return; const i = document.createElement('input'); i.maxLength = 80; i.className = 'mb'; i.placeholder = 'Вариант ' + (box.children.length + 1); box.appendChild(i); return i; };
    add(); add(); $('#v3-padd', md).onclick = () => add()?.focus(); $('#v3-pq', md).focus();
    $('#v3-pgo', md).onclick = async () => {
      const options = $$('input', box).map(i => i.value.trim()).filter(Boolean);
      try { await A.api(`/v3/chat/${encodeURIComponent(u)}/poll`, { question: $('#v3-pq', md).value, options, multi: $('#v3-pm', md).checked ? '1' : '' }); md.classList.remove('open'); await window.poll?.(); } catch (e) {}
    };
  }

  // ================================================================ эффекты сообщений
  const FX = [['confetti', 'Конфетти', '🎉'], ['hearts', 'Сердечки', '❤️'], ['snow', 'Снег', '❄️'], ['fireworks', 'Салют', '🎆']];
  on('[data-v3-effects]', () => {
    const inp = $('#inp');
    if (!inp || !inp.value.trim()) { A.toast('Сначала напишите сообщение'); inp?.focus(); return; }
    const md = A.modal('Отправить с эффектом', `<div class="v3-fxpick">${FX.map(f => `<button type="button" data-fx="${f[0]}"><span>${f[2]}</span>${f[1]}</button>`).join('')}</div>`);
    $$('[data-fx]', md).forEach(b => b.onclick = () => { md.classList.remove('open'); window._sendExtra = { effect: b.dataset.fx }; play(b.dataset.fx); $('.cmp-send')?.click(); });
  });
  function play(kind) {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const layer = document.createElement('div'); layer.className = 'v3-fx v3-fx-' + kind; document.body.appendChild(layer);
    const sym = { confetti: null, hearts: '❤', snow: '❄', fireworks: null }[kind], colors = ['#2f6487', '#c2552f', '#c98a1b', '#3c9a5f', '#f7ead7', '#1f1d1a'];
    const n = kind === 'fireworks' ? 5 : 46;
    for (let i = 0; i < n; i++) {
      const p = document.createElement('i');
      if (kind === 'fireworks') {
        p.className = 'burst'; p.style.left = (12 + Math.random() * 76) + '%'; p.style.top = (12 + Math.random() * 45) + '%'; p.style.animationDelay = (i * 0.32) + 's';
        for (let k = 0; k < 14; k++) { const s = document.createElement('b'); s.style.setProperty('--a', (k * 360 / 14) + 'deg'); s.style.background = colors[(i + k) % colors.length]; p.appendChild(s); }
      } else {
        p.style.left = Math.random() * 100 + '%'; p.style.animationDelay = Math.random() * 1.2 + 's'; p.style.animationDuration = (2.2 + Math.random() * 1.8) + 's';
        if (sym) { p.textContent = sym; p.style.fontSize = (12 + Math.random() * 16) + 'px'; } else { p.style.background = colors[i % colors.length]; p.style.transform = `rotate(${Math.random() * 360}deg)`; }
      }
      layer.appendChild(p);
    }
    setTimeout(() => layer.remove(), 4800);
  }
  // новое входящее сообщение с эффектом проигрывается один раз (и только если ему меньше суток)
  const seenFx = new Set(store.get('v3fx', []));
  function scanFx(root) {
    $$('.msg[data-effect]', root).forEach(m => {
      if (m.dataset.v3fx || seenFx.has(m.dataset.id)) return; m.dataset.v3fx = '1';
      seenFx.add(m.dataset.id); store.set('v3fx', [...seenFx].slice(-200));
      if (!m.classList.contains('mine') && Date.now() / 1000 - (+m.dataset.ts || 0) < 86400) play(m.dataset.effect);
    });
  }
  const box = $('#box');
  if (box) {
    // уже показанные при открытии чата старые сообщения не взрываются заново — только самое свежее непросмотренное
    const fresh = $$('.msg[data-effect]', box).filter(m => !seenFx.has(m.dataset.id));
    fresh.slice(0, -1).forEach(m => { seenFx.add(m.dataset.id); m.dataset.v3fx = '1'; });
    scanFx(box);
    new MutationObserver(() => scanFx(box)).observe(box, { childList: true });
  }

  // ================================================================ папки чатов
  const fbar = $('#v3-folders');
  if (fbar) {
    let folders = [], cur = store.get('v3folder', '');
    const chats = JSON.parse(fbar.dataset.chats || '[]');
    const apply = () => {
      const f = folders.find(x => String(x.id) === String(cur));
      $$('.chat[data-user]').forEach(c => c.classList.toggle('v3-off', !!f && !f.members.includes(c.dataset.user.toLowerCase())));
      $$('.chat[data-kind=group]').forEach(c => c.classList.toggle('v3-off', !!f));
      $$('[data-folder]', fbar).forEach(b => b.classList.toggle('active', String(b.dataset.folder) === String(f ? f.id : '')));
    };
    const draw = () => {
      $$('[data-folder]:not([data-folder=""])', fbar).forEach(b => b.remove());
      const add = $('[data-folder-new]', fbar);
      folders.forEach(f => { const b = document.createElement('button'); b.type = 'button'; b.className = 'chip'; b.dataset.folder = f.id; b.textContent = f.name + ' · ' + f.members.length; b.title = 'Долгое нажатие — изменить'; fbar.insertBefore(b, add); });
      apply();
    };
    const load = async () => { try { folders = (await A.get('/v3/folders')).folders; } catch (e) { folders = []; } if (!folders.some(f => String(f.id) === String(cur))) cur = ''; draw(); };
    const edit = f => {
      const md = A.modal(f ? 'Папка «' + f.name + '»' : 'Новая папка', `<input id="v3-fn" maxlength="30" placeholder="Название: Семья, Учёба…" value="${A.esc(f ? f.name : '')}">
        <div class="v3-fchats mt">${chats.length ? chats.map(u => `<label class="check"><input type="checkbox" value="${A.esc(u)}"${f && f.members.includes(u.toLowerCase()) ? ' checked' : ''}><span>@${A.esc(u)}</span></label>`).join('') : '<div class="empty small">Сначала начните переписку</div>'}</div>
        <button class="btn block mt" id="v3-fgo">Сохранить</button>${f ? '<button class="btn ghost block mt danger" id="v3-fdel">Удалить папку</button>' : ''}`);
      $('#v3-fn', md).focus();
      $('#v3-fgo', md).onclick = async () => {
        const members = $$('.v3-fchats input:checked', md).map(i => i.value);
        try { const r = await A.api('/v3/folders', { id: f ? f.id : '', name: $('#v3-fn', md).value, members }); md.classList.remove('open'); cur = r.id; store.set('v3folder', cur); load(); } catch (e) {}
      };
      if (f) $('#v3-fdel', md).onclick = async () => { if (!confirm('Удалить папку? Чаты останутся.')) return; await A.api(`/v3/folders/${f.id}/delete`); md.classList.remove('open'); cur = ''; store.set('v3folder', ''); load(); };
    };
    let lp = 0;
    fbar.addEventListener('pointerdown', e => { const b = e.target.closest('[data-folder]'); if (!b || !b.dataset.folder) return; lp = setTimeout(() => { lp = -1; edit(folders.find(x => String(x.id) === b.dataset.folder)); }, 500); });
    fbar.addEventListener('pointerup', () => { if (lp > 0) clearTimeout(lp); });
    fbar.addEventListener('contextmenu', e => { const b = e.target.closest('[data-folder]'); if (b && b.dataset.folder) { e.preventDefault(); edit(folders.find(x => String(x.id) === b.dataset.folder)); } });
    fbar.addEventListener('click', e => {
      if (e.target.closest('[data-folder-new]')) { edit(null); return; }
      const b = e.target.closest('[data-folder]'); if (!b) return;
      if (lp === -1) { lp = 0; return; }
      cur = b.dataset.folder; store.set('v3folder', cur); apply();
    });
    load();
  }

  // ================================================================ капсула: сколько осталось до вскрытия
  $$('.v3-cap-left[data-v3-ts]').forEach(el => { const left = +el.dataset.v3Ts; el.textContent = left > 86400 ? 'через ' + plural(Math.ceil(left / 86400), 'день', 'дня', 'дней') : 'скоро'; });
  on('[data-v3-hide]', async b => {
    const u = b.dataset.v3Hide;
    if (!confirm(`Не показывать посты @${u} 30 дней? Подписка останется.`)) return;
    try { await A.api(`/v3/hide/${encodeURIComponent(u)}`); A.toast('Скрыто на 30 дней'); $$('.post').forEach(p => { if (p.querySelector(`[data-v3-hide="${CSS.escape(u)}"]`)) p.remove(); }); } catch (e) {}
  });

  // ================================================================ сундук
  on('[data-v3-chest]', async b => {
    b.disabled = true;
    try {
      const r = await A.api('/v3/chest');
      b.classList.add('opened'); b.innerHTML = `${IC('check')}<span>+${r.reward}</span>`;
      A.toast(`Сундук открыт: +${r.reward} искр · серия ${plural(r.streak, 'день', 'дня', 'дней')}`); play('confetti');
      setTimeout(() => b.remove(), 2500);
    } catch (e) { b.disabled = false; }
  });

  // ================================================================ капсула времени
  const capF = $('#v3-capsule-form');
  if (capF) {
    const dt = $('#v3-cap-date');
    const t = new Date(Date.now() + 864e5); dt.min = t.toISOString().slice(0, 10);
    capF.addEventListener('change', () => dt.classList.toggle('hidden', capF.period.value !== 'date'));
    capF.addEventListener('submit', async e => { e.preventDefault(); try { await A.api('/capsule', formData(capF)); A.toast('Письмо запечатано'); setTimeout(() => location.reload(), 500); } catch (err) {} });
  }
  on('[data-v3-capdel]', async b => { if (!confirm('Удалить письмо?')) return; try { await A.api(`/capsule/${b.dataset.v3Capdel}/delete`); b.closest('.v3-letter').remove(); } catch (e) {} });

  // ================================================================ «Словечко»
  const wg = $('#v3-word');
  if (wg) {
    let st = JSON.parse(wg.dataset.state), typed = '', busy = false;
    const msgEl = $('#v3-wmsg'), kb = $('#v3-kb');
    const draw = () => {
      let html = '';
      for (let r = 0; r < 6; r++) {
        const row = st.rows[r], cur = !row && r === st.rows.length && !st.over;
        html += '<div class="v3-wrow' + (cur ? ' cur' : '') + '">';
        for (let i = 0; i < 5; i++) { const ch = row ? row.word[i] : cur ? (typed[i] || '') : ''; html += `<span class="${row ? row.score[i] : ch ? 'f' : ''}">${A.esc(ch)}</span>`; }
        html += '</div>';
      }
      wg.innerHTML = html;
      const best = {};
      st.rows.forEach(r => [...r.word].forEach((ch, i) => { const s = r.score[i], o = best[ch]; if (s === 'g' || (s === 'y' && o !== 'g') || (!o)) best[ch] = s === 'g' ? 'g' : (o === 'g' ? 'g' : (s === 'y' || o === 'y') ? 'y' : 'n'); }));
      $$('[data-k]', kb).forEach(b => { b.className = (b.classList.contains('wide') ? 'wide ' : '') + (best[b.dataset.k] || ''); });
      msgEl.textContent = st.solved ? `Угадано с ${st.rows.length}-й попытки! Новое слово — завтра.` : st.over ? `Не получилось. Слово дня: «${(st.answer || '').toUpperCase()}». Завтра будет новое.` : '';
      $('#v3-wshare').classList.toggle('hidden', !st.over);
    };
    const press = async k => {
      if (st.over || busy) return;
      if (k === '⌫' || k === 'Backspace') typed = typed.slice(0, -1);
      else if (k === '⏎' || k === 'Enter') {
        if (typed.length < 5) { msgEl.textContent = 'Нужно 5 букв'; wg.querySelector('.cur')?.classList.add('shake'); setTimeout(() => wg.querySelector('.cur')?.classList.remove('shake'), 400); return; }
        busy = true;
        try { const r = await A.api('/games/word/guess', { word: typed }); st = r; typed = ''; if (r.solved) play('confetti'); } catch (e) {}
        busy = false;
      } else if (/^[а-яё]$/i.test(k) && typed.length < 5) typed += k.toLowerCase().replace('ё', 'е');
      draw();
    };
    kb.addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (b) press(b.dataset.k); });
    document.addEventListener('keydown', e => { if (e.ctrlKey || e.metaKey || e.altKey || e.target.closest('input,textarea')) return; press(e.key); });
    $('#v3-wshare').onclick = () => {
      const grid = st.rows.map(r => [...r.score].map(s => ({ g: '🟩', y: '🟨', n: '⬜' }[s])).join('')).join('\n');
      const text = `Словечко ${st.solved ? st.rows.length : 'X'}/6\n${grid}\n${location.origin}/games/word`;
      if (navigator.share) navigator.share({ text }).catch(() => {}); else navigator.clipboard?.writeText(text).then(() => A.toast('Результат скопирован'));
    };
    draw();
  }

  // ================================================================ 2048
  const gb = $('#g-board');
  if (gb) {
    let grid, score, over, best = +gb.dataset.best || 0, sent = 0;
    const KEY = 'v3-2048';
    const scoreEl = $('#g-score'), bestEl = $('#g-best');
    const empty = () => { const r = []; grid.forEach((row, y) => row.forEach((v, x) => { if (!v) r.push([y, x]); })); return r; };
    const spawn = () => { const e = empty(); if (!e.length) return; const [y, x] = e[Math.floor(Math.random() * e.length)]; grid[y][x] = Math.random() < 0.9 ? 2 : 4; return [y, x]; };
    const fresh = () => { grid = [...Array(4)].map(() => [0, 0, 0, 0]); score = 0; over = false; spawn(); spawn(); };
    const saved = store.get(KEY, null);
    if (saved && saved.grid) { grid = saved.grid; score = saved.score; over = false; } else fresh();
    const canMove = () => empty().length || grid.some((row, y) => row.some((v, x) => (x < 3 && v === row[x + 1]) || (y < 3 && v === grid[y + 1][x])));
    const draw = (born) => {
      gb.innerHTML = grid.map((row, y) => row.map((v, x) => `<div class="t${v ? ' v' + Math.min(v, 4096) : ''}${born && born[0] === y && born[1] === x ? ' born' : ''}">${v || ''}</div>`).join('')).join('') + (over ? `<div class="g-over"><b>Ходов нет</b><span>Счёт: ${score}</span><button class="btn sm" type="button" data-g-new>Ещё раз</button></div>` : '');
      scoreEl.textContent = score; bestEl.textContent = Math.max(best, score);
      store.set(KEY, over ? null : { grid, score });
    };
    const submit = async () => { if (score <= best || score <= sent) return; sent = score; try { const r = await A.api('/games/2048/score', { score }); best = r.best; if (r.record) A.toast('Новый рекорд: ' + r.best); } catch (e) {} };
    const slide = row => { const a = row.filter(Boolean); for (let i = 0; i < a.length - 1; i++) if (a[i] === a[i + 1]) { a[i] *= 2; score += a[i]; a.splice(i + 1, 1); } while (a.length < 4) a.push(0); return a; };
    const move = dir => {
      if (over) return;
      const before = JSON.stringify(grid);
      for (let i = 0; i < 4; i++) {
        let line = dir === 'L' || dir === 'R' ? grid[i].slice() : grid.map(r => r[i]);
        if (dir === 'R' || dir === 'D') line.reverse();
        line = slide(line);
        if (dir === 'R' || dir === 'D') line.reverse();
        if (dir === 'L' || dir === 'R') grid[i] = line; else line.forEach((v, y) => { grid[y][i] = v; });
      }
      if (JSON.stringify(grid) === before) return;
      const born = spawn();
      if (!canMove()) { over = true; submit(); }
      draw(born);
      if (score > best && score - sent >= 500) submit();
    };
    document.addEventListener('keydown', e => { const d = { ArrowLeft: 'L', ArrowRight: 'R', ArrowUp: 'U', ArrowDown: 'D' }[e.key]; if (d && !e.target.closest('input,textarea')) { e.preventDefault(); move(d); } });
    let sx = 0, sy = 0;
    gb.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }, { passive: true });
    gb.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
    gb.addEventListener('touchend', e => { const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy; if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) return; move(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'R' : 'L') : (dy > 0 ? 'D' : 'U')); });
    const restart = () => { submit(); fresh(); draw(); };
    $('#g-new').onclick = restart;
    gb.addEventListener('click', e => { if (e.target.closest('[data-g-new]')) restart(); });
    addEventListener('pagehide', () => { if (score > best && score > sent && navigator.sendBeacon) { const fd = new FormData(); fd.append('score', score); navigator.sendBeacon('/games/2048/score', fd); } });
    draw();
  }

  // ================================================================ резервные коды
  on('[data-v3-backup]', async b => {
    if (b.dataset.done === '1' || (b.textContent.includes('новые') && !confirm('Старые коды перестанут работать. Создать новые?'))) return;
    try {
      const r = await A.api('/v3/backup-codes'); const pre = $('#v3-codes');
      pre.textContent = r.codes.join('\n'); pre.classList.remove('hidden');
      b.dataset.done = '1'; b.textContent = 'Скопировать коды';
      b.onclick = () => navigator.clipboard?.writeText(r.codes.join('\n')).then(() => A.toast('Коды скопированы — сохраните их в надёжном месте'));
      A.toast('Сохраните коды — больше они не покажутся');
    } catch (e) {}
  });

  // ================================================================ группировка уведомлений
  const gt = $('#v3-group');
  if (gt) {
    const GROUPABLE = { like: 'оценили ваш пост', whale: 'отправили кита вашему посту', comment: 'прокомментировали ваш пост', repost: 'сделали репост вашего поста', follow: 'подписались на вас', comment_like: 'оценили ваш комментарий' };
    const rows = $$('[data-ntype]');
    const group = enabled => {
      rows.forEach(r => { r.classList.remove('v3-ghide'); r.querySelector('.v3-gsum')?.remove(); });
      if (!enabled) return;
      let i = 0;
      while (i < rows.length) {
        const r = rows[i], t = r.dataset.ntype, p = r.dataset.npost; let j = i + 1;
        if (GROUPABLE[t]) while (j < rows.length && rows[j].dataset.ntype === t && rows[j].dataset.npost === p) j++;
        const n = j - i - 1;
        if (n > 0) {
          for (let k = i + 1; k < j; k++) rows[k].classList.add('v3-ghide');
          const names = [...new Set(rows.slice(i, j).map(x => x.dataset.nname).filter(Boolean))];
          const s = document.createElement('div'); s.className = 'v3-gsum small';
          s.innerHTML = `<b>${A.esc(names[0] || '')}</b> и ещё ${plural(names.length - 1 || n, 'человек', 'человека', 'человек')} ${GROUPABLE[t]} <button type="button" class="v3-link">показать</button>`;
          s.querySelector('button').onclick = () => { for (let k = i + 1; k < j; k++) rows[k].classList.remove('v3-ghide'); s.remove(); };
          r.querySelector('.grow')?.prepend(s);
        }
        i = j;
      }
    };
    gt.checked = store.get('v3group', true);
    gt.addEventListener('change', () => { store.set('v3group', gt.checked); group(gt.checked); });
    group(gt.checked);
  }

  // ================================================================ поиск по помощи
  const hq = $('#v3-help-q');
  if (hq) {
    const filter = () => {
      const q = hq.value.trim().toLowerCase(); let shown = 0;
      $$('.v3-hitem').forEach(d => { const ok = !q || q.split(/\s+/).every(w => d.dataset.text.includes(w)); d.classList.toggle('hidden', !ok); if (ok) shown++; if (q && ok && shown <= 2) d.open = true; });
      $$('.v3-hsec').forEach(s => { let n = s.nextElementSibling, any = false; while (n && !n.classList.contains('v3-hsec')) { if (!n.classList.contains('hidden')) any = true; n = n.nextElementSibling; } s.classList.toggle('hidden', !any); });
      $('#v3-help-none').classList.toggle('hidden', shown > 0);
    };
    hq.addEventListener('input', () => { filter(); const ai = $('#v3-help-ai'); if (ai) ai.href = '/ai' + (hq.value.trim() ? '?q=' + encodeURIComponent(hq.value.trim()) : ''); }); filter();
  }
})();

/* Нува: простой помощник и «Исправить текст» / «Подобрать хэштеги» в редакторе поста */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s), A = window.App;
  const IC = n => (window.ICON ? ICON(n, 'i in') : '');
  const paras = t => A.esc(t).replace(/\n/g, '<br>');
  document.addEventListener('click', e => {
    const rw = e.target.closest('[data-ai-rewrite]');
    if (!rw) return;
    const ta = rw.closest('form')?.querySelector('textarea[name=content]');
    if (!ta || ta.value.trim().length < 3) { A.toast('Сначала напишите текст поста'); ta?.focus(); return; }
    const md = A.modal('Помощник Нува', `<button type="button" class="btn soft block mb" data-m="fix">${IC('check')} Исправить текст</button><button type="button" class="btn soft block" data-m="tags">${IC('hash')} Подобрать хэштеги</button><div class="tiny faint mt">Исправляет частые ошибки, пробелы, запятые и заглавные буквы. Проверьте результат перед публикацией.</div>`);
    md.querySelectorAll('[data-m]').forEach(b => b.onclick = async () => {
      try {
        const r = await A.api('/ai/rewrite', { text: ta.value, mode: b.dataset.m });
        if (r.same) { A.toast('Ошибок не нашлось'); md.classList.remove('open'); return; }
        $('.b', md).innerHTML = `<div class="ai-out" style="white-space:pre-wrap">${A.esc(r.text)}</div><div class="row mt" style="gap:8px"><button class="btn grow" id="ai-use">Заменить текст</button><button class="btn soft" id="ai-no">Отмена</button></div>`;
        $('#ai-use', md).onclick = () => { ta.value = r.text; ta.dispatchEvent(new Event('input', { bubbles: true })); md.classList.remove('open'); ta.focus(); };
        $('#ai-no', md).onclick = () => md.classList.remove('open');
      } catch (err) { md.classList.remove('open'); }
    });
  });

  // страница /ai
  const form = $('#ai-form');
  if (!form) return;
  const log = $('#ai-log'), inp = $('#ai-in'), sugg = $('#ai-sugg'), KEY = 'nuva-history';
  let hist = [];
  try { hist = JSON.parse(localStorage.getItem(KEY) || '[]').slice(-40); } catch (e) { hist = []; }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(hist.slice(-40))); } catch (e) {} };
  const add = (role, text, links) => {
    const d = document.createElement('div'); d.className = 'ai-msg ' + (role === 'user' ? 'me' : 'bot'); d.innerHTML = paras(text);
    if (links && links.length) d.innerHTML += '<div class="ai-links">' + links.map(l => `<a class="btn soft sm" href="${A.esc(l.url)}">${A.esc(l.title)}</a>`).join('') + '</div>';
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  };
  const tips = list => { sugg.innerHTML = (list || []).map(t => `<button type="button" class="chip" data-ai-q>${A.esc(t)}</button>`).join(''); sugg.classList.toggle('hidden', !(list || []).length); };
  hist.forEach(h => add(h.role, h.content, h.links));
  if (hist.length) sugg.classList.add('hidden');
  async function send(text) {
    text = text.trim(); if (!text) return;
    add('user', text); hist.push({ role: 'user', content: text });
    inp.value = ''; inp.style.height = 'auto';
    const prev = [...hist].reverse().find((h, i) => i > 0 && h.role === 'user');
    const wait = document.createElement('div'); wait.className = 'ai-msg bot ai-typing'; wait.innerHTML = '<i></i><i></i><i></i>'; log.appendChild(wait); log.scrollTop = log.scrollHeight;
    try { const r = await A.api('/ai/chat', { question: text, prev: prev ? prev.content : '', history: JSON.stringify(hist.slice(-9, -1).map(h => ({ role: h.role, content: h.content }))) }); wait.remove(); add('bot', r.text, r.links); hist.push({ role: 'bot', content: r.text, links: r.links }); tips(r.tips); }
    catch (e) { wait.remove(); hist.pop(); inp.value = text; }
    save();
  }
  form.addEventListener('submit', e => { e.preventDefault(); send(inp.value); });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(inp.value); } });
  inp.addEventListener('input', () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 140) + 'px'; });
  sugg.addEventListener('click', e => { const b = e.target.closest('[data-ai-q]'); if (b) send(b.textContent); });
  $('#ai-clear').onclick = () => { hist = []; save(); log.querySelectorAll('.ai-msg:not(:first-child)').forEach(x => x.remove()); tips(['Что ты умеешь?', 'Как создать опрос в чате?', 'Подпись к фото с моря', 'Идея для поста']); };
  if (inp.dataset.q) send(inp.dataset.q);
})();

/* /ai/admin: обучение Нувы */
(function () {
  const f = document.getElementById('nuva-form');
  if (!f) return;
  const A = window.App;
  document.addEventListener('click', async e => {
    const ans = e.target.closest('[data-nuva-answer]'), del = e.target.closest('[data-nuva-del]'), edit = e.target.closest('[data-nuva-edit]');
    if (ans) { f.reset(); f.id.value = ''; f.miss_id.value = ans.dataset.nuvaAnswer; f.question.value = ans.dataset.q; f.scrollIntoView({ behavior: 'smooth' }); f.answer.focus(); }
    if (edit) { const d = JSON.parse(edit.dataset.nuvaEdit); Object.keys(d).forEach(k => { if (f[k]) f[k].value = d[k] || ''; }); f.miss_id.value = ''; f.scrollIntoView({ behavior: 'smooth' }); }
    if (del) {
      if (!confirm(del.dataset.kind === 'answer' ? 'Удалить ответ?' : 'Убрать вопрос из списка?')) return;
      try { await A.api(`/ai/admin/${del.dataset.kind}/${del.dataset.nuvaDel}/delete`); del.closest('.nuva-row').remove(); } catch (err) {}
    }
  });
  f.addEventListener('submit', async e => {
    e.preventDefault();
    try { const r = await A.api('/ai/admin/answer', Object.fromEntries(new FormData(f).entries())); A.toast('Ответ сохранён' + (r.solved ? ` · закрыто вопросов: ${r.solved}` : '')); setTimeout(() => location.reload(), 700); } catch (err) {}
  });
})();

/* Движение 3.1 и «как приложение»: волна от касания, прыгающие счётчики, плавная смена темы, баннер «Нет сети» */
(function () {
  'use strict';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('p-reduce-motion');
  const inApp = /NuvoraApp\//.test(navigator.userAgent);
  // волна от касания на кнопках
  if (!reduce) document.addEventListener('pointerdown', e => {
    const el = e.target.closest('.btn, .chip, .icon-btn, .tool, .mobile-nav a, .v3-opt, .today-chest, .v3-kb button, .tabs a');
    if (!el || el.disabled) return;
    const r = el.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2.2;
    const w = document.createElement('span'); w.className = 'm-ripple';
    w.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    el.classList.add('m-rippled'); el.appendChild(w); setTimeout(() => w.remove(), 600);
    if (inApp && el.closest('.mobile-nav')) navigator.vibrate?.(6);
  }, { passive: true });
  // счётчик лайка подпрыгивает после нажатия (без слежки за всей страницей — так легче для телефона)
  if (!reduce) document.addEventListener('click', e => {
    const a = e.target.closest('.act'); if (!a) return;
    setTimeout(() => { const n = a.querySelector('.n'); if (n) { n.classList.remove('bump'); void n.offsetWidth; n.classList.add('bump'); } }, 120);
  });
  // в приложении — без переходов-«снимков» между страницами: WebView делает их медленно
  if (inApp) addEventListener('pagereveal', e => { try { e.viewTransition && e.viewTransition.skipTransition(); } catch (er) {} });
  // плавная смена темы
  const tt = window.toggleTheme;
  if (typeof tt === 'function') window.toggleTheme = function () { const h = document.documentElement; h.classList.add('m-theme'); const r = tt.apply(this, arguments); setTimeout(() => h.classList.remove('m-theme'), 450); return r; };
  // нет сети / сеть вернулась
  let bar = null, hideT = 0;
  const show = (off) => {
    if (!bar) { bar = document.createElement('div'); bar.className = 'm-offline'; document.body.appendChild(bar); }
    bar.classList.toggle('back', !off); bar.innerHTML = `<i></i>${off ? 'Нет сети — показываю сохранённое' : 'Снова в сети'}`;
    requestAnimationFrame(() => bar.classList.add('show')); clearTimeout(hideT);
    if (!off) hideT = setTimeout(() => bar.classList.remove('show'), 2200);
  };
  // список сохранённых страниц для офлайн-экрана приложения
  try {
    const okPath = /^\/($|messages\/?$|notifications$|explore$|games(\/2048|\/word)?$|help$|ai$|capsule$|bookmarks$|whats-new$|profile\/[\w.-]+$|post\/\d+$|messages\/[\w.-]+$)/;
    if (window.APP && APP.user && okPath.test(location.pathname) && navigator.onLine) {
      const u = location.pathname + location.search, t = u === '/' ? 'Лента' : (document.title || '').replace(/\s*—\s*Nuvora\s*$/, '') || 'Страница';
      const list = JSON.parse(localStorage.getItem('nv_saved_pages') || '[]').filter(p => p.u !== u);
      list.unshift({ u, t }); localStorage.setItem('nv_saved_pages', JSON.stringify(list.slice(0, 12)));
    }
  } catch (e) {}
  // navigator.onLine в WebView часто врёт (переключение Wi-Fi и 4G, VPN), поэтому «нет сети» показываем
  // только если сервер действительно не отвечает, и сами проверяем, когда связь вернулась
  let offline = false, recheck = 0, checking = false;
  async function verify() {
    if (checking) return; checking = true;
    let ok = false;
    try {
      const c = new AbortController(), t = setTimeout(() => c.abort(), 6000);
      const r = await fetch('/healthz?ts=' + Date.now(), { cache: 'no-store', signal: c.signal });
      clearTimeout(t); ok = !!r; // любой ответ сервера — значит, сеть есть
    } catch (e) { ok = false; }
    checking = false;
    if (!ok && !offline) { offline = true; show(true); }
    if (ok && offline) { offline = false; show(false); }
    clearInterval(recheck);
    if (offline) recheck = setInterval(verify, 5000);
  }
  addEventListener('offline', () => setTimeout(verify, 1500));
  addEventListener('online', verify);
  if (!navigator.onLine) setTimeout(verify, 1500);
})();

/* Красивые логины: покупка за искры */
(function () {
  const A = window.App;
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-v3-handle]'); if (!b) return;
    const name = b.dataset.v3Handle, price = +b.dataset.price;
    const md = A.modal('@' + name, `<p class="small muted mb">Можно сделать @${A.esc(name)} основным логином (старый освободится) или добавить дополнительным — у одного человека до трёх логинов.</p>
      <input type="password" id="v3-hpass" placeholder="Пароль для подтверждения" autocomplete="current-password">
      <button class="btn block mt" data-mode="main">Сделать основным · ${price} искр</button><button class="btn soft block mt" data-mode="alias">Добавить дополнительным · ${price} искр</button>`);
    md.querySelector('#v3-hpass').focus();
    md.querySelectorAll('[data-mode]').forEach(btn => btn.onclick = async () => {
      try {
        const r = await A.api('/handles/buy', { username: name, password: md.querySelector('#v3-hpass').value, mode: btn.dataset.mode });
        md.classList.remove('open'); A.toast(r.alias ? '@' + name + ' — ваш дополнительный логин' : 'Теперь вы @' + r.username);
        setTimeout(() => location.href = '/profile/' + r.username, 700);
      } catch (err) {}
    });
  });
})();

/* Дополнительные логины в настройках */
(function () {
  const A = window.App, f = document.getElementById('v3-alias-form');
  if (f) f.addEventListener('submit', async e => { e.preventDefault(); try { await A.api('/settings/aliases/add', Object.fromEntries(new FormData(f).entries())); location.reload(); } catch (err) {} });
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-v3-alias]'); if (!b) return;
    const h = b.dataset.v3Alias, a = b.dataset.a;
    if (!confirm(a === 'delete' ? `Отказаться от @${h}? Его сможет занять кто-то другой.` : `Сделать @${h} основным логином? Нынешний станет дополнительным.`)) return;
    try { await A.api(`/settings/aliases/${encodeURIComponent(h)}/${a}`); location.reload(); } catch (err) {}
  });
})();

/* «Поделился(ась) с вами» и «позвал(а) вас»: добавить в друзья одним нажатием */
(function () {
  'use strict';
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-share-follow]');
    if (b) {
      b.disabled = true;
      try { await App.api('/follow/' + encodeURIComponent(b.dataset.shareFollow)); b.textContent = 'Добавлен(а)'; App.toast('Теперь вы подписаны'); if (b.dataset.dismiss) App.api('/v3/suggest-follow/dismiss').catch(() => {}); }
      catch (er) { b.disabled = false; }
      return;
    }
    if (e.target.closest('[data-sg-close]')) { document.getElementById('sg-card')?.remove(); App.api('/v3/suggest-follow/dismiss').catch(() => {}); }
  });
})();
