/* Статус у имени для Nuvora+: нажал на свой значок у имени — маленькое окно, где его можно поменять.
   На чужой значок — подсказка, что это такое. Список стикеров — /plus/status.json. */
(function () {
  let pop = null, data = null;
  const me = () => document.body.dataset.me || '';
  const close = () => { if (pop) { pop.remove(); pop = null; } };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function place(el, anchor) {
    document.body.appendChild(el);
    const r = anchor.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight, vw = innerWidth, vh = innerHeight;
    let x = Math.min(Math.max(12, r.left - 20), vw - w - 12), y = r.bottom + 8;
    if (y + h > vh - 12) y = Math.max(12, r.top - h - 8);
    el.style.left = x + 'px'; el.style.top = y + 'px';
    el.style.transformOrigin = `${r.left + r.width / 2 - x}px ${y > r.top ? 0 : h}px`;
  }

  function setMine(img) {  // обновить все свои значки на странице
    document.querySelectorAll(`.badge[data-es="${CSS.escape(me())}"]`).forEach(b => {
      if (img) { b.className = 'badge estatus'; b.innerHTML = `<img src="${img}" alt="">`; }
      else { b.className = 'badge plus-b'; b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5c.8 5.1 2.6 7 7.7 7.8-5.1.8-6.9 2.6-7.7 7.7-.8-5.1-2.6-6.9-7.7-7.7 5.1-.8 6.9-2.7 7.7-7.8z"/></svg>'; }
    });
  }

  async function picker(anchor) {
    if (!data) { try { data = await App.api('/plus/status.json', undefined, { method: 'GET' }); } catch (e) { return; } }
    close();
    pop = document.createElement('div'); pop.className = 'es-pop';
    if (!data.plus) {
      pop.innerHTML = '<div class="es-pop-note"><b>Статус у имени — для Nuvora+</b><br>Получить Nuvora+ можно за <a href="/tasks" style="color:var(--link)">задания и розыгрыш недели</a>.</div>';
      place(pop, anchor); return;
    }
    pop.innerHTML = `<div class="es-pop-h"><span class="grow">Статус у имени</span>${data.current ? '<button class="btn ghost sm" data-clear>Убрать</button>' : ''}<button class="icon-btn" data-x aria-label="Закрыть">✕</button></div>
      <div class="es-pop-tabs">${data.groups.map((g, i) => `<button type="button" data-tab="${i}" title="${esc(g.title)}" class="${i ? '' : 'on'}"><img src="${g.items[0][1]}" alt=""></button>`).join('')}</div>
      <div class="es-pop-b">${data.groups.map((g, i) => `<h4 data-g="${i}">${esc(g.title)}</h4><div class="es-pop-g">${g.items.map(([id, img, t]) => `<button type="button" data-id="${id}" title="${esc(t)}" class="${id === data.current ? 'on' : ''}"><img src="${img}" alt="" loading="lazy"></button>`).join('')}</div>`).join('')}</div>`;
    place(pop, anchor);
    const body = pop.querySelector('.es-pop-b'), tabs = pop.querySelectorAll('[data-tab]');
    tabs.forEach(t => t.onclick = () => { body.scrollTo({ top: body.querySelector(`[data-g="${t.dataset.tab}"]`).offsetTop - 4, behavior: 'smooth' }); });
    body.addEventListener('scroll', () => {
      let cur = 0; body.querySelectorAll('h4').forEach((h, i) => { if (h.offsetTop - 30 <= body.scrollTop) cur = i; });
      tabs.forEach((t, i) => t.classList.toggle('on', i === cur));
    }, { passive: true });
    const pick = async id => {
      try { const r = await App.api('/plus/status', { id }); data.current = id; setMine(r.img); close(); App.toast(id ? 'Статус поставлен' : 'Статус убран'); } catch (e) {}
    };
    pop.querySelectorAll('[data-id]').forEach(b => b.onclick = () => pick(b.dataset.id));
    const c = pop.querySelector('[data-clear]'); if (c) c.onclick = () => pick('');
    pop.querySelector('[data-x]').onclick = close;
  }

  function info(anchor) {
    close();
    pop = document.createElement('div'); pop.className = 'es-pop';
    const img = anchor.querySelector('img');
    pop.innerHTML = `<div class="es-pop-note" style="text-align:center">${img ? `<img src="${img.src}" alt="">` : ''}<b>Статус Nuvora+</b><br><span class="small muted">С Nuvora+ у имени можно поставить свой стикер — их больше двухсот.</span>${me() ? '<br><a class="btn sm mt" href="/plus/status">Выбрать свой</a>' : ''}</div>`;
    place(pop, anchor);
  }

  document.addEventListener('click', e => {
    const b = e.target.closest('.badge[data-es]');
    if (b) {
      e.preventDefault(); e.stopPropagation();
      if (pop && pop._for === b) { close(); return; }
      const open = me() && b.dataset.es === me() ? picker : info;
      Promise.resolve(open(b)).then(() => { if (pop) pop._for = b; });
      return;
    }
    if (pop && !pop.contains(e.target)) close();
  }, true);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  addEventListener('scroll', e => { if (pop && !pop.contains(e.target)) close(); }, { passive: true, capture: true });
})();
