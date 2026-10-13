/* Общий клиентский код. Всё навешивается через data-атрибуты и делегирование событий. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ME = window.APP || {};

  // ---------- Утилиты ----------
  async function api(url, data, opts = {}) {
    const init = { method: opts.method || 'POST', headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' };
    if (data instanceof FormData) init.body = data;
    else if (data !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(data); }
    if (opts.method === 'GET') delete init.body;
    const res = await fetch(url, init);
    let json = {};
    try { json = await res.json(); } catch (e) { json = { ok: res.ok }; }
    if (res.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname); throw new Error('auth'); }
    if (!res.ok || json.ok === false) { const err = json.error || 'Ошибка'; toast(err, true); throw new Error(err); }
    return json;
  }
  const get = (url) => api(url, undefined, { method: 'GET' });
  function toast(text, isError) {
    let box = $('#toasts');
    if (!box) { box = document.createElement('div'); box.id = 'toasts'; document.body.appendChild(box); }
    const t = document.createElement('div');
    t.className = 'toast' + (isError ? ' error' : '');
    t.textContent = text;
    box.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }
  function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function avatarHtml(u, size = 36) {
    const inner = u.avatar ? `<img src="${esc(u.avatar)}" alt="">` : `<span style="font-size:${Math.round(size * .4)}px">${esc((u.username || '?')[0].toUpperCase())}</span>`;
    return `<span class="av" style="width:${size}px;height:${size}px">${inner}</span>`;
  }
  window.App = { api, get, toast, esc, avatarHtml };

  // ---------- Тема ----------
  function applyTheme(t) {
    const real = t === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : t;
    document.documentElement.setAttribute('data-theme', real);
    const meta = $('meta[name=theme-color]');
    if (meta) meta.content = real === 'dark' ? '#0b0b12' : '#ffffff';
  }
  window.toggleTheme = function () {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('theme', next); } catch (e) {}
    applyTheme(next);
    if (ME.user) fetch('/settings/theme', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme: next }) });
  };
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    let t = ME.theme || 'light';
    try { t = localStorage.getItem('theme') || t; } catch (e) {}
    if (t === 'auto') applyTheme('auto');
  });

  // ---------- Меню и модалки ----------
  document.addEventListener('click', (e) => {
    const toggle = e.target.closest('[data-menu]');
    $$('.menu.open').forEach(m => { if (!toggle || m !== toggle.nextElementSibling) m.classList.remove('open'); });
    if (toggle) { e.preventDefault(); toggle.nextElementSibling?.classList.toggle('open'); }
    const close = e.target.closest('[data-close]');
    if (close || e.target.classList.contains('modal-bg')) (close?.closest('.modal-bg') || e.target).classList.remove('open');
    const openM = e.target.closest('[data-modal]');
    if (openM) { e.preventDefault(); $('#' + openM.dataset.modal)?.classList.add('open'); }
  });
  function modal(title, html) {
    let bg = $('#app-modal');
    if (!bg) {
      bg = document.createElement('div'); bg.id = 'app-modal'; bg.className = 'modal-bg';
      bg.innerHTML = '<div class="modal"><div class="modal-head"><span class="t"></span><button class="icon-btn" data-close>✕</button></div><div class="b"></div></div>';
      document.body.appendChild(bg);
    }
    $('.t', bg).textContent = title; $('.b', bg).innerHTML = html; bg.classList.add('open');
    return bg;
  }
  window.App.modal = modal;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { $$('.modal-bg.open, .lightbox.open').forEach(m => m.classList.remove('open')); $$('.menu.open').forEach(m => m.classList.remove('open')); } });

  // ---------- Лайтбокс ----------
  document.addEventListener('click', (e) => {
    const img = e.target.closest('img[data-zoom]');
    if (!img) return;
    let lb = $('#lightbox');
    if (!lb) { lb = document.createElement('div'); lb.id = 'lightbox'; lb.className = 'lightbox'; lb.innerHTML = '<img alt="">'; lb.onclick = () => lb.classList.remove('open'); document.body.appendChild(lb); }
    $('img', lb).src = img.src; lb.classList.add('open');
  });

  // ---------- Действия с постами ----------
  function bump(el) { el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop'); }
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act, id = b.dataset.id;
    if (!ME.user && !['share', 'expand', 'copy'].includes(act)) { location.href = '/login?next=' + encodeURIComponent(location.pathname); return; }
    e.preventDefault();
    try {
      if (act === 'like' || act === 'whale' || act === 'bookmark') {
        const url = act === 'bookmark' ? `/bookmark/${id}` : `/${act}/${id}`;
        const r = await api(url);
        const on = act === 'like' ? r.liked : act === 'whale' ? r.whaled : r.bookmarked;
        b.classList.toggle('on', on); bump(b);
        const c = $('.n', b); if (c && r.count !== undefined) c.textContent = r.count;
        if (act === 'bookmark') toast(on ? 'Добавлено в закладки' : 'Удалено из закладок');
      } else if (act === 'repost') {
        const r = await api(`/repost/${id}`, {});
        b.classList.toggle('on', r.reposted); const c = $('.n', b); if (c) c.textContent = r.count;
        toast(r.reposted ? 'Репост сделан' : 'Репост отменён');
      } else if (act === 'quote') {
        const m = modal('Цитировать пост', `<textarea id="quote-text" maxlength="1000" placeholder="Добавьте комментарий..."></textarea><button class="btn block mt" id="quote-send">Опубликовать</button>`);
        $('#quote-send', m).onclick = async () => { const t = $('#quote-text', m).value.trim(); if (!t) return; await api(`/repost/${id}`, { comment: t }); m.classList.remove('open'); toast('Опубликовано'); };
      } else if (act === 'react-open') {
        const wrap = b.parentElement; let p = $('.react-picker', wrap);
        if (p) { p.remove(); return; }
        p = document.createElement('div'); p.className = 'react-picker';
        p.innerHTML = (ME.reactions || []).map(r => `<button data-act="react" data-id="${id}" data-emoji="${r}">${r}</button>`).join('');
        wrap.appendChild(p);
      } else if (act === 'react') {
        const r = await api(`/post/${id}/react`, { emoji: b.dataset.emoji });
        b.closest('.react-picker')?.remove();
        const bar = $(`#reactions-${id}`);
        if (bar) bar.innerHTML = Object.entries(r.counts).map(([em, n]) => `<button class="reaction-pill ${r.mine === em ? 'mine' : ''}" data-act="react" data-id="${id}" data-emoji="${em}">${em} <b>${n}</b></button>`).join('');
      } else if (act === 'share' || act === 'copy') {
        const url = location.origin + (b.dataset.url || `/post/${id}`);
        if (act === 'share' && navigator.share) { try { await navigator.share({ url }); } catch (er) {} }
        else { await navigator.clipboard.writeText(url); toast('Ссылка скопирована'); }
      } else if (act === 'expand') {
        $(`#text-${id}`)?.classList.remove('clamp'); b.remove();
      } else if (act === 'delete-post') {
        if (!confirm('Удалить пост?')) return;
        await api(`/post/${id}/delete`); const el = $(`#post-${id}`); if (el) el.remove(); else location.href = '/'; toast('Пост удалён');
      } else if (act === 'edit-post') {
        const txt = $(`#raw-${id}`)?.value || '';
        const m = modal('Редактировать пост', `<textarea id="edit-text" maxlength="5000" style="min-height:140px">${esc(txt)}</textarea><button class="btn block mt" id="edit-save">Сохранить</button>`);
        $('#edit-save', m).onclick = async () => { await api(`/post/${id}/edit`, { content: $('#edit-text', m).value }); location.reload(); };
      } else if (act === 'pin-post') {
        const r = await api(`/post/${id}/pin`); toast(r.pinned ? 'Закреплено в профиле' : 'Откреплено');
      } else if (act === 'report-post') {
        const reasons = ['Спам', 'Оскорбления', 'Насилие', 'Обман', '18+', 'Другое'];
        const m = modal('Пожаловаться', reasons.map(r => `<button class="btn soft block mb" data-reason="${r}">${r}</button>`).join(''));
        $$('[data-reason]', m).forEach(x => x.onclick = async () => { await api(`/post/${id}/report`, { reason: x.dataset.reason }); m.classList.remove('open'); toast('Жалоба отправлена, спасибо!'); });
      } else if (act === 'likers') {
        const r = await get(`/api/post/${id}/likers`);
        modal('Понравилось', r.hidden ? '<div class="empty">Автор скрыл лайки</div>' : (r.users.length ? r.users.map(u => `<a class="user-row" href="/profile/${esc(u.username)}">${avatarHtml(u, 40)}<div class="info"><b>${esc(u.name)}</b><div class="bio">@${esc(u.username)}</div></div></a>`).join('') : '<div class="empty">Пока никто</div>'));
      } else if (act === 'vote') {
        const r = await api(`/poll/vote/${id}`);
        const box = b.closest('.poll'); const total = r.total || 1;
        r.options.forEach(o => {
          const el = $(`[data-opt="${o.id}"]`, box); if (!el) return;
          const pct = Math.round(o.votes / total * 100);
          el.classList.add('done'); if (o.id == id) el.classList.add('mine');
          el.removeAttribute('data-act');
          $('.bar', el).style.width = pct + '%'; $('.pct', el).textContent = pct + '%';
        });
        $('.poll-total', box).textContent = r.total + ' голос(ов)';
      } else if (act === 'follow') {
        const r = await api(`/follow/${b.dataset.user}`);
        const labels = { following: 'Вы подписаны', requested: 'Заявка отправлена', none: 'Подписаться' };
        b.textContent = labels[r.state]; b.classList.toggle('ghost', r.state !== 'none');
        const fc = $('#followers-count'); if (fc) fc.textContent = r.followers;
      } else if (act === 'comment-like') {
        const r = await api(`/comment/${id}/like`); b.classList.toggle('on', r.liked); $('.n', b).textContent = r.count || '';
      } else if (act === 'comment-delete') {
        if (!confirm('Удалить комментарий?')) return; await api(`/comment/${id}/delete`); $(`#comment-${id}`)?.remove();
      } else if (act === 'comment-pin') {
        await api(`/post/${b.dataset.post}/pin-comment/${id}`); location.reload();
      } else if (act === 'reply') {
        const f = $('#comment-form'); if (!f) return;
        f.parent_id.value = id; $('#reply-to-label').textContent = 'Ответ для @' + b.dataset.user; $('#reply-to').classList.remove('hidden');
        f.content.focus();
      } else if (act === 'not-interested') {
        await api(`/post/${id}/not-interested`); const el = $(`#post-${id}`);
        if (el) { const prev = el.previousElementSibling; if (prev && prev.classList.contains('rec-reason')) prev.remove(); el.remove(); }
        toast('Понял, буду показывать такое реже');
      } else if (act === 'toggle') {
        const r = await api(b.dataset.url); toast(b.dataset.msg || 'Готово');
        if (b.dataset.reload) location.reload();
      }
    } catch (err) { /* тост уже показан */ }
  });

  // формы с data-ajax: отправка без перезагрузки
  document.addEventListener('submit', async (e) => {
    const f = e.target.closest('form[data-ajax]');
    if (!f) return;
    e.preventDefault();
    const btn = $('button[type=submit], button:not([type])', f); if (btn) btn.disabled = true;
    try {
      const fd = new FormData(f);
      const r = await api(f.action, fd);
      if (f.dataset.success) toast(f.dataset.success);
      if (f.dataset.reload !== undefined) location.reload();
      else if (f.dataset.redirect) location.href = f.dataset.redirect.replace('{id}', r.id || r.post_id || '');
      else f.reset();
      f.dispatchEvent(new CustomEvent('ajax:done', { detail: r }));
    } catch (err) {} finally { if (btn) btn.disabled = false; }
  });

  // ---------- Автодополнение @упоминаний и #тегов ----------
  function attachSuggest(el) {
    if (el.dataset.suggestReady) return; el.dataset.suggestReady = 1;
    const box = document.createElement('div'); box.className = 'suggest'; document.body.appendChild(box);
    let items = [], sel = 0, token = null, timer;
    function close() { box.classList.remove('open'); items = []; token = null; }
    function render() {
      if (!items.length) return close();
      box.innerHTML = items.map((it, i) => `<div class="${i === sel ? 'sel' : ''}" data-i="${i}">${it.html}</div>`).join('');
      const r = el.getBoundingClientRect();
      box.style.left = (r.left + window.scrollX) + 'px'; box.style.top = (r.bottom + window.scrollY + 4) + 'px'; box.style.width = Math.min(r.width, 320) + 'px';
      box.classList.add('open');
    }
    function pick(i) {
      const it = items[i]; if (!it || !token) return;
      const v = el.value, pos = el.selectionStart;
      el.value = v.slice(0, token.start) + it.insert + ' ' + v.slice(pos);
      const np = token.start + it.insert.length + 1; el.setSelectionRange(np, np); el.focus(); close();
      el.dispatchEvent(new Event('input'));
    }
    box.addEventListener('mousedown', (e) => { const d = e.target.closest('[data-i]'); if (d) { e.preventDefault(); pick(+d.dataset.i); } });
    el.addEventListener('keydown', (e) => {
      if (!box.classList.contains('open')) return;
      if (e.key === 'ArrowDown') { sel = (sel + 1) % items.length; render(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = (sel - 1 + items.length) % items.length; render(); e.preventDefault(); }
      else if (e.key === 'Enter' || e.key === 'Tab') { pick(sel); e.preventDefault(); }
      else if (e.key === 'Escape') close();
    });
    el.addEventListener('blur', () => setTimeout(close, 150));
    el.addEventListener('input', () => {
      const before = el.value.slice(0, el.selectionStart);
      const m = before.match(/(^|\s)([@#])([\wА-яЁё]{0,30})$/);
      if (!m) return close();
      token = { start: before.length - m[3].length - 1, kind: m[2], q: m[3] };
      clearTimeout(timer);
      timer = setTimeout(async () => {
        try {
          if (token.kind === '@') {
            const r = await get('/api/users/suggest?q=' + encodeURIComponent(token.q));
            items = r.users.map(u => ({ insert: '@' + u.username, html: `${avatarHtml(u, 26)}<b>${esc(u.name)}</b><span class="muted small">@${esc(u.username)}</span>` }));
          } else {
            const r = await get('/api/hashtags/suggest?q=' + encodeURIComponent(token.q));
            items = r.tags.map(t => ({ insert: '#' + t.tag, html: `<b>#${esc(t.tag)}</b><span class="muted small">${t.count}</span>` }));
          }
          sel = 0; render();
        } catch (e) { close(); }
      }, 160);
    });
  }
  window.App.attachSuggest = attachSuggest;
  $$('[data-suggest]').forEach(attachSuggest);

  // ---------- Композер постов ----------
  const composer = $('#composer');
  if (composer) {
    const ta = $('textarea[name=content]', composer), input = $('#composer-files'), previews = $('#composer-previews');
    const counter = $('#composer-counter'), max = +ta.getAttribute('maxlength') || 5000;
    let files = [];
    const autosize = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 420) + 'px'; };
    ta.addEventListener('input', () => {
      autosize(); const left = max - ta.value.length;
      counter.textContent = ta.value.length ? left : ''; counter.className = 'counter' + (left < 0 ? ' over' : left < 200 ? ' warn' : '');
      try { localStorage.setItem('composer-draft', ta.value); } catch (e) {}
    });
    try { const saved = localStorage.getItem('composer-draft'); if (saved && !ta.value) { ta.value = saved; autosize(); } } catch (e) {}
    function drawPreviews() {
      previews.innerHTML = '';
      files.forEach((f, i) => {
        const url = URL.createObjectURL(f), d = document.createElement('div'); d.className = 'pv';
        d.innerHTML = (f.type.startsWith('video') ? `<video src="${url}" muted></video>` : `<img src="${url}" alt="">`) + `<button type="button" data-i="${i}">✕</button>`;
        previews.appendChild(d);
      });
      previews.classList.toggle('hidden', !files.length);
    }
    previews.addEventListener('click', (e) => { const b = e.target.closest('button[data-i]'); if (b) { files.splice(+b.dataset.i, 1); drawPreviews(); } });
    input.addEventListener('change', () => {
      for (const f of input.files) {
        if (files.length >= 10) { toast('Максимум 10 файлов', true); break; }
        const lim = f.type.startsWith('video') ? 100 : 10;
        if (f.size > lim * 1024 * 1024) { toast(`«${f.name}» больше ${lim} МБ`, true); continue; }
        files.push(f);
      }
      input.value = ''; drawPreviews();
    });
    // вставка картинок из буфера
    ta.addEventListener('paste', (e) => {
      for (const it of e.clipboardData?.items || []) if (it.type.startsWith('image/')) { const f = it.getAsFile(); if (f && files.length < 10) files.push(f); }
      drawPreviews();
    });
    $$('[data-panel]', composer).forEach(b => b.addEventListener('click', () => {
      const p = $('#' + b.dataset.panel); p.classList.toggle('hidden'); b.classList.toggle('on', !p.classList.contains('hidden'));
    }));
    $('#add-poll-option')?.addEventListener('click', () => {
      const wrap = $('#poll-options'); if ($$('input', wrap).length >= 6) return;
      const i = document.createElement('input'); i.name = 'poll_options'; i.placeholder = 'Вариант ' + ($$('input', wrap).length + 1); i.maxLength = 100; wrap.appendChild(i);
    });
    $$('[data-emoji-insert]', composer).forEach(b => b.addEventListener('click', () => {
      const p = ta.selectionStart; ta.value = ta.value.slice(0, p) + b.textContent + ta.value.slice(p); ta.focus(); ta.dispatchEvent(new Event('input'));
    }));
    $('#save-draft')?.addEventListener('click', async () => {
      if (!ta.value.trim()) return toast('Черновик пустой', true);
      await api('/drafts/save', { content: ta.value, draft_id: $('[name=draft_id]', composer).value });
      try { localStorage.removeItem('composer-draft'); } catch (e) {}
      toast('Черновик сохранён'); ta.value = ''; ta.dispatchEvent(new Event('input'));
    });
    composer.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(composer); fd.delete('media'); files.forEach(f => fd.append('media', f));
      const btn = $('#composer-submit'); btn.disabled = true; btn.textContent = files.length ? 'Загрузка…' : 'Публикуем…';
      try {
        const r = await api('/post/create', fd);
        try { localStorage.removeItem('composer-draft'); } catch (er) {}
        toast(r.held ? '🛡 ' + r.message : r.scheduled ? 'Пост запланирован ⏰' : 'Опубликовано ✨');
        setTimeout(() => location.href = r.scheduled ? '/drafts' : `/post/${r.post_id}`, 400);
      } catch (err) { btn.disabled = false; btn.textContent = 'Опубликовать'; }
    });
    $$('[data-draft-load]').forEach(a => a.addEventListener('click', (e) => {
      e.preventDefault(); ta.value = a.dataset.content; $('[name=draft_id]', composer).value = a.dataset.draftLoad; ta.focus(); ta.dispatchEvent(new Event('input'));
    }));
  }

  // ---------- Бесконечная лента ----------
  function setupInfinite() {
    const sentinel = $('[data-more]');
    if (!sentinel) return;
    const manual = (ME.prefs || {}).infinite_scroll === false || !('IntersectionObserver' in window);
    if (manual) {  // настройка «Бесконечная прокрутка» выключена — грузим по кнопке
      sentinel.innerHTML = '<button class="btn soft manual-more">Показать ещё</button>';
      sentinel.addEventListener('click', () => load([{ isIntersecting: true }]));
    }
    const load = async (entries) => {
      if (!entries[0].isIntersecting || sentinel.dataset.loading) return;
      sentinel.dataset.loading = 1;
      try {
        const res = await fetch(sentinel.dataset.more, { headers: { 'X-Requested-With': 'fetch' } });
        const html = await res.text();
        const tmp = document.createElement('div'); tmp.innerHTML = html;
        const next = $('[data-more]', tmp);
        sentinel.before(...Array.from(tmp.childNodes).filter(n => n !== next));
        if (next) { sentinel.dataset.more = next.dataset.more; delete sentinel.dataset.loading; }
        else { if (io) io.disconnect(); sentinel.textContent = 'Вы всё посмотрели ✨'; }
        document.dispatchEvent(new Event('app:content'));
      } catch (e) { delete sentinel.dataset.loading; }
    };
    const io = manual ? null : new IntersectionObserver(load, { rootMargin: '600px' });
    if (io) io.observe(sentinel);
  }
  setupInfinite();

  // ---------- Активный пункт меню ----------
  const path = location.pathname;
  $$('.nav-item, .mobile-nav a').forEach(a => {
    const h = a.getAttribute('href');
    if (h && (path === h || (h !== '/' && path.startsWith(h)))) a.classList.add('active');
  });

  if (!ME.user) return;

  // ---------- Счётчики и онлайн ----------
  function setBadge(sel, n) { $$(sel).forEach(b => { b.textContent = n > 99 ? '99+' : n; b.classList.toggle('hidden', !n); }); }
  let lastNotif = ME.unread || 0;
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await (await fetch('/api/counters', { headers: { 'X-Requested-With': 'fetch' } })).json();
      if (!r.ok) return;
      setBadge('[data-badge=notifications]', r.notifications); setBadge('[data-badge=messages]', r.messages);
      if (r.notifications > lastNotif && ME.sound) beep();
      lastNotif = r.notifications;
      const clean = document.title.replace(/^\(\d+\)\s/, '');
      document.title = ((ME.prefs || {}).title_badge !== false && r.notifications + r.messages ? `(${r.notifications + r.messages}) ` : '') + clean;
    } catch (e) {}
  }
  setInterval(poll, 20000);
  function beep() { try { const c = new AudioContext(), o = c.createOscillator(), g = c.createGain(); o.connect(g); g.connect(c.destination); o.frequency.value = 880; g.gain.setValueAtTime(.08, c.currentTime); g.gain.exponentialRampToValueAtTime(.0001, c.currentTime + .25); o.start(); o.stop(c.currentTime + .25); } catch (e) {} }


  // ---------- Горячие клавиши ----------
  let gPressed = false;
  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, textarea, select') || e.metaKey || e.ctrlKey || e.altKey) return;
    if ((ME.prefs || {}).hotkeys === false) return;
    if (e.key === 'n') { const t = $('#composer textarea'); if (t) { e.preventDefault(); t.focus(); } else location.href = '/create'; }
    else if (e.key === '/') { e.preventDefault(); location.href = '/search'; }
    else if (e.key === '?') { modal('Горячие клавиши', `<div class="stack small"><div><span class="kbd">n</span> — новый пост</div><div><span class="kbd">/</span> — поиск</div><div><span class="kbd">g</span> <span class="kbd">h</span> — лента</div><div><span class="kbd">g</span> <span class="kbd">m</span> — сообщения</div><div><span class="kbd">g</span> <span class="kbd">n</span> — уведомления</div><div><span class="kbd">g</span> <span class="kbd">p</span> — профиль</div><div><span class="kbd">g</span> <span class="kbd">e</span> — обзор</div><div><span class="kbd">t</span> — сменить тему</div></div>`); }
    else if (e.key === 't') toggleTheme();
    else if (e.key === 'g') { gPressed = true; setTimeout(() => gPressed = false, 900); }
    else if (gPressed) {
      const map = { h: '/', m: '/messages', n: '/notifications', p: '/profile/' + ME.user, e: '/explore', s: '/settings', b: '/bookmarks' };
      if (map[e.key]) location.href = map[e.key];
      gPressed = false;
    }
  });

  // ---------- Service worker + push ----------
  function b64ToUint8(b64) { const pad = '='.repeat((4 - b64.length % 4) % 4); const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from([...raw].map(c => c.charCodeAt(0))); }
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(async (reg) => {
      if (!ME.push || !('PushManager' in window)) return;
      window.enablePush = async function () {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') return toast('Уведомления запрещены в браузере', true);
        const { key } = await (await fetch('/api/vapid-public-key')).json();
        if (!key) return;
        const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(key) });
        const j = sub.toJSON();
        await api('/api/push/subscribe', { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth });
        toast('Push-уведомления включены 🔔');
      };
      if (Notification.permission === 'granted') { try { await window.enablePush(); } catch (e) {} }
    }).catch(() => {});
  }
})();


// ---------- Настройки пользователя, которые работают в браузере (services/prefs.py) ----------
(function () {
  const P = (window.APP && window.APP.prefs) || {};
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const MEDIA = '.post .media img, .post .media video, .post .media-grid img, .post .media-grid video';

  // Размытие медиа: первое нажатие открывает, а не увеличивает
  if (P.blur_media) document.addEventListener('click', (e) => {
    const m = e.target.closest(MEDIA);
    if (m && !m.classList.contains('revealed')) { e.preventDefault(); e.stopPropagation(); m.classList.add('revealed'); }
  }, true);

  // Лайк двойным нажатием на фото
  if (P.double_tap_like !== false) document.addEventListener('dblclick', (e) => {
    const m = e.target.closest('.post .media img, .post .media-grid img'); if (!m) return;
    const like = m.closest('.post').querySelector('[data-act=like]');
    if (like && !like.classList.contains('on')) like.click();
    const h = document.createElement('div'); h.className = 'dbl-heart'; h.textContent = '❤️';
    h.style.cssText = `position:fixed;left:${e.clientX - 30}px;top:${e.clientY - 40}px;font-size:60px;pointer-events:none;z-index:999;transition:all .6s;`;
    document.body.appendChild(h); requestAnimationFrame(() => { h.style.transform = 'translateY(-40px) scale(1.4)'; h.style.opacity = '0'; });
    setTimeout(() => h.remove(), 700);
  });

  // Внешние ссылки — в новой вкладке
  if (P.links_new_tab !== false) document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="http"]');
    if (a && a.host !== location.host && !a.target) { a.target = '_blank'; a.rel = 'noopener nofollow'; }
  }, true);

  function apply(root) {
    // Автовоспроизведение видео без звука
    if (P.autoplay_video !== false && 'IntersectionObserver' in window) {
      const io = apply.io || (apply.io = new IntersectionObserver((es) => es.forEach(en => {
        const v = en.target; if (en.isIntersecting && en.intersectionRatio > .6) { v.muted = true; v.play().catch(() => {}); } else if (!v.paused) v.pause();
      }), { threshold: [0, .6] }));
      $$('.post video:not([data-ap])', root).forEach(v => { v.dataset.ap = 1; v.loop = true; io.observe(v); });
    }
    // Точное время вместо «5 мин назад»
    if (P.absolute_time) $$('.time[title]:not([data-abs])', root).forEach(t => { t.dataset.abs = 1; t.textContent = t.title.replace(' UTC', ''); });
    // Крупные эмодзи в чатах
    if (P.chat_big_emoji !== false) $$('.bubble:not([data-em]) .txt', root).forEach(t => {
      const b = t.closest('.bubble'); b.dataset.em = 1;
      const txt = t.textContent.trim();
      if (txt && txt.length <= 12 && /^(\p{Extended_Pictographic}|\p{Emoji_Component}|‍|️|\s)+$/u.test(txt) && !b.querySelector('img,video,audio,.file')) b.classList.add('big-emoji');
    });
    // Подсказки у кнопок-иконок
    if (P.alt_hints !== false) $$('.icon-btn[aria-label]:not([title])', root).forEach(b => b.title = b.getAttribute('aria-label'));
  }
  apply(document);
  document.addEventListener('app:content', () => apply(document));
  if ('MutationObserver' in window) {
    let t; new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => apply(document), 120); }).observe(document.body, { childList: true, subtree: true });
  }
})();
