/* Чаты «как в Telegram»: видео с первым кадром и кнопкой ▶, плавное появление новых сообщений (tgchat.css). */
(function () {
  'use strict';
  const fmt = s => { s = Math.max(0, Math.round(s || 0)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  function prep(root) {
    (root || document).querySelectorAll('.tgv video:not([data-tg])').forEach(v => {
      v.dataset.tg = '1';
      const dur = v.parentNode.querySelector('.tgv-dur');
      const set = () => { if (isFinite(v.duration) && v.duration > 0) dur.textContent = fmt(v.duration); };
      v.addEventListener('loadedmetadata', set); set();
    });
  }
  document.addEventListener('click', e => {
    const b = e.target.closest('.tgv-play'); if (!b) return;
    const box = b.closest('.tgv'), v = box.querySelector('video');
    document.querySelectorAll('.tgv.playing video').forEach(o => { if (o !== v) o.pause(); });
    box.classList.add('playing'); v.muted = false; v.controls = true; v.play().catch(() => {});
  });
  document.addEventListener('DOMContentLoaded', () => {
    prep();
    const box = document.getElementById('box'); if (!box) return;
    let ready = false; setTimeout(() => ready = true, 1500);
    new MutationObserver(list => {
      for (const r of list) for (const n of r.addedNodes) {
        if (n.nodeType !== 1) continue;
        prep(n);
        if (ready && n.classList && n.classList.contains('msg')) { n.classList.add('tg-new'); setTimeout(() => n.classList.remove('tg-new'), 400); }
      }
    }).observe(box, { childList: true, subtree: true });
  });
})();

/* Список чатов всегда свежий: при возврате жестом «назад» (браузер показывает сохранённую страницу),
   при возвращении в приложение и раз в 20 секунд — подтягиваем новый список, не перезагружая страницу. */
(function () {
  'use strict';
  let busy = false, last = Date.now();
  async function refreshList() {
    const list = document.getElementById('chat-list'); if (!list || busy) return;
    busy = true;
    try {
      const r = await fetch(location.pathname + location.search, { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) return;
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      const fresh = doc.getElementById('chat-list');
      if (fresh && fresh.innerHTML !== list.innerHTML) {
        list.innerHTML = fresh.innerHTML;
        try {  // черновики, как при обычной загрузке (more.js)
          list.querySelectorAll('.chat[data-uid]').forEach(row => { const d = JSON.parse(localStorage.getItem('nv_draft_' + row.dataset.uid) || '""'); const pv = row.querySelector('.preview');
            if (d && pv) { pv.textContent = ''; const t = document.createElement('span'); t.className = 'draft-tag'; t.textContent = 'Черновик:'; pv.append(t, ' ' + String(d).slice(0, 80)); pv.classList.add('has-draft'); } });
        } catch (e) {}
        const chip = document.querySelector('#chat-tabs .chip.active'); chip && chip.click();
      }
      last = Date.now();
    } catch (e) {} finally { busy = false; }
  }
  if (!document.getElementById('chat-list')) return;
  addEventListener('pageshow', e => { if (e.persisted) refreshList(); });
  try { if ((performance.getEntriesByType('navigation')[0] || {}).type === 'back_forward') refreshList(); } catch (e) {}
  document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - last > 3000) refreshList(); });
  setInterval(() => { if (!document.hidden) refreshList(); }, 20000);
})();
