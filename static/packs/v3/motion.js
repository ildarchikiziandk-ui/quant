/* Лёгкие анимации (7.11.2026, motion.css): фото проявляются после загрузки, счётчики подпрыгивают,
   у лайка — искорка. Ничего не делает при «Уменьшить движение». */
(function () {
  const root = document.documentElement;
  if (root.classList.contains('p-reduce-motion') || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  // фото: если ещё не загрузилось — прячем и плавно показываем по готовности
  const fade = img => {
    if (img.complete || img.dataset.nvf) return;
    img.dataset.nvf = '1'; img.classList.add('nv-fade');
    const show = () => { img.classList.add('nv-in'); img.classList.remove('nv-fade'); };
    img.addEventListener('load', show, { once: true }); img.addEventListener('error', show, { once: true });
  };
  const SEL = '.post-media img, .ntile img, .att img, .ph-grid img, .v3-sticker';
  document.querySelectorAll(SEL).forEach(fade);
  new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) { if (n.matches && n.matches(SEL)) fade(n); n.querySelectorAll && n.querySelectorAll(SEL).forEach(fade); } })
    .observe(document.body, { childList: true, subtree: true });
  // счётчики: число изменилось — «подпрыжка»
  document.querySelectorAll('[data-badge]').forEach(b => {
    let last = b.textContent;
    new MutationObserver(() => { if (b.textContent !== last && b.textContent.trim() && b.textContent !== '0') { b.classList.remove('nv-pop'); void b.offsetWidth; b.classList.add('nv-pop'); } last = b.textContent; })
      .observe(b, { childList: true, characterData: true, subtree: true });
  });
  // лайк, кит, закладка — искорка в момент нажатия «включить»
  document.addEventListener('click', e => {
    const a = e.target.closest('.act.like, .act.whale, .act[data-act="bookmark"]'); if (!a || a.classList.contains('on')) return;
    a.classList.remove('nv-burst'); void a.offsetWidth; a.classList.add('nv-burst'); setTimeout(() => a.classList.remove('nv-burst'), 600);
  }, true);
})();
