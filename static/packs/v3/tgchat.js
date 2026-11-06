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
