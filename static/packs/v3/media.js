/* Сжатие видео перед отправкой в чат: большие ролики перекодируются прямо на телефоне (до 720p, ~1,2 Мбит/с),
   чтобы отправлялись быстрее и меньше весили. Где браузер так не умеет (iPhone), отправляется как есть. */
(function () {
  'use strict';
  const MIN_SIZE = 12 * 1024 * 1024, MAX_SECONDS = 600, MAX_SIDE = 1280;

  function panel(onSkip) {
    const el = document.createElement('div');
    el.className = 'nv-shrink';
    el.innerHTML = '<div class="nv-shrink-t">Сжимаем видео… <b>0%</b></div><div class="nv-shrink-bar"><i></i></div><button type="button" class="btn sm soft">Отправить как есть</button>';
    el.querySelector('button').onclick = onSkip;
    document.body.appendChild(el);
    return { set: p => { el.querySelector('b').textContent = Math.round(p * 100) + '%'; el.querySelector('i').style.width = (p * 100) + '%'; }, close: () => el.remove() };
  }

  window.nvShrinkVideo = function (file) {
    return new Promise(resolve => {
      const v = document.createElement('video');
      const cap = v.captureStream ? 'captureStream' : v.mozCaptureStream ? 'mozCaptureStream' : '';
      const mime = window.MediaRecorder && ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']
        .find(t => { try { return MediaRecorder.isTypeSupported(t); } catch (e) { return false; } });
      if (!file || !/^video\//.test(file.type) || file.size < MIN_SIZE || !cap || !mime || !HTMLCanvasElement.prototype.captureStream) return resolve(file);
      const url = URL.createObjectURL(file);
      let done = false, ui = null, rec = null, raf = 0;
      const finish = out => {
        if (done) return; done = true;
        cancelAnimationFrame(raf); try { v.pause(); } catch (e) {} URL.revokeObjectURL(url); if (ui) ui.close();
        resolve(out && out.size && out.size < file.size ? out : file);
      };
      v.muted = true; v.playsInline = true; v.preload = 'auto'; v.src = url;
      v.onerror = () => finish(null);
      v.onloadedmetadata = async () => {
        if (!v.duration || !isFinite(v.duration) || v.duration > MAX_SECONDS || !v.videoWidth) return finish(null);
        const k = Math.min(1, MAX_SIDE / Math.max(v.videoWidth, v.videoHeight));
        const c = document.createElement('canvas'); c.width = Math.round(v.videoWidth * k / 2) * 2; c.height = Math.round(v.videoHeight * k / 2) * 2;
        const g = c.getContext('2d');
        const stream = c.captureStream(30);
        try { v[cap]().getAudioTracks().forEach(t => stream.addTrack(t)); } catch (e) {}
        const chunks = [];
        try { rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 1200000, audioBitsPerSecond: 96000 }); } catch (e) { return finish(null); }
        rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
        rec.onstop = () => {
          if (done) return;
          const type = mime.split(';')[0], ext = type === 'video/mp4' ? '.mp4' : '.webm';
          finish(new File(chunks, (file.name || 'video').replace(/\.[^.]+$/, '') + ext, { type }));
        };
        ui = panel(() => finish(null));
        const draw = () => { g.drawImage(v, 0, 0, c.width, c.height); ui.set(v.currentTime / v.duration); if (!v.ended) raf = requestAnimationFrame(draw); };
        v.onended = () => { try { rec.state !== 'inactive' && rec.stop(); } catch (e) { finish(null); } };
        try { await v.play(); } catch (e) { return finish(null); }
        rec.start(1000); draw();
      };
    });
  };
})();

/* Стикеры «Кит Нуви»: панель над полем ввода, по нажатию — отправка */
(function () {
  'use strict';
  let pack = null, panel = null;
  async function load() {
    if (pack) return pack;
    try { pack = (await (await fetch('/v3/stickers', { headers: { 'X-Requested-With': 'fetch' } })).json()).stickers || []; } catch (e) { pack = []; }
    return pack;
  }
  async function send(btn, id) {
    const marker = `[[v3:st:${id}]]`;
    try {
      if (btn.dataset.to) await App.api('/messages/send', { receiver: btn.dataset.to, content: marker });
      else if (btn.dataset.group) { const fd = new FormData(); fd.append('content', marker); await App.api(`/groups/${btn.dataset.group}/send`, fd); }
      if (typeof window.poll === 'function') await window.poll();
      const box = document.getElementById('box') || document.querySelector('.convo-box'); if (box) box.scrollTop = box.scrollHeight;
    } catch (e) {}
  }
  function close() { if (panel) { panel.remove(); panel = null; } }
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-stickers]');
    if (!btn) { if (panel && !e.target.closest('.nv-stickers')) close(); return; }
    e.preventDefault();
    if (panel) return close();
    const list = await load();
    panel = document.createElement('div');
    panel.className = 'nv-stickers';
    panel.innerHTML = '<div class="nv-stickers-h">Кит Нуви</div><div class="nv-stickers-g">' +
      list.map(s => `<button type="button" data-st="${s.id}" title="${s.name}"><img src="${s.url}" alt="${s.name}" loading="lazy"></button>`).join('') + '</div>';
    panel.addEventListener('click', ev => { const b = ev.target.closest('[data-st]'); if (b) { close(); send(btn, b.dataset.st); } });
    const host = btn.closest('.cmp, .convo-input, form') || document.body;
    if (host !== document.body && getComputedStyle(host).position === 'static') host.style.position = 'relative';
    host.appendChild(panel);
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
})();

/* Компактное поле ввода: все инструменты (вложение, стикеры, опрос, эффект) — в меню за одной кнопкой «+»,
   эмодзи — внутри поля. В строке остаются только «+», поле и микрофон/отправка. */
(function () {
  'use strict';
  const NAMES = { 'Фото или файл': ['clip', 'Фото, видео или файл'], 'Вложение': ['clip', 'Фото, видео или файл'], 'Стикеры': ['whale', 'Стикеры'],
    'Опрос или игра': ['poll', 'Опрос или игра'], 'Сообщение с эффектом': ['sparkle', 'Сообщение с эффектом'] };
  const sprite = () => { const u = document.querySelector('use[href*="icons.svg"]'); return u ? u.getAttribute('href').split('#')[0] : '/static/icons.svg'; };
  const ico = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="${sprite()}#${n}"/></svg>`;
  let open = null;
  const close = () => { if (open) { open.classList.remove('show'); open = null; } document.querySelectorAll('.cmp-plus.on').forEach(b => b.classList.remove('on')); };

  function compact(row) {
    if (row.dataset.compact) return;
    row.dataset.compact = '1';
    const tools = [...row.querySelectorAll(':scope > .cmp-tool')];
    const ta = row.querySelector(':scope > textarea');
    if (!ta || !tools.length) return;
    const emoji = tools.find(t => t.title === 'Эмодзи');
    const menuTools = tools.filter(t => t !== emoji);
    // эмодзи — внутри поля
    const field = document.createElement('div');
    field.className = 'cmp-field';
    ta.parentNode.insertBefore(field, ta); field.appendChild(ta);
    if (emoji) { emoji.classList.add('cmp-emoji'); field.appendChild(emoji); }
    if (!menuTools.length) return;
    // «+» и меню
    const plus = document.createElement('button');
    plus.type = 'button'; plus.className = 'icon-btn cmp-plus'; plus.title = 'Прикрепить'; plus.setAttribute('aria-label', 'Прикрепить');
    plus.innerHTML = ico('plus');
    const menu = document.createElement('div');
    menu.className = 'cmp-menu';
    menuTools.forEach(t => {
      const [ic, label] = NAMES[t.title] || ['plus', t.title || 'Ещё'];
      const it = document.createElement('button');
      it.type = 'button'; it.innerHTML = ico(ic) + `<span>${label}</span>`;
      it.addEventListener('click', e => { e.stopPropagation(); close(); t.click(); });
      menu.appendChild(it);
    });
    row.insertBefore(plus, field);
    row.closest('.cmp, form, .convo-input')?.appendChild(menu);
    plus.addEventListener('click', e => { e.stopPropagation(); if (open === menu) return close(); close(); menu.classList.add('show'); open = menu; plus.classList.add('on'); });
  }
  document.addEventListener('click', e => { if (open && !e.target.closest('.cmp-menu')) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  const run = () => document.querySelectorAll('.cmp-row').forEach(compact);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
