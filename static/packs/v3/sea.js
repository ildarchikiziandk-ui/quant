/* Морской бой: расстановка своего флота перед партией (packs/v3/chat_games.py → /v3/game/<id>/sea/place).
   Выберите корабль внизу, нажмите клетку — корабль встанет оттуда вправо (или вниз после «Повернуть»).
   Нажатие на поставленный корабль убирает его. Корабли не должны касаться друг друга даже углами. */
(function () {
  'use strict';
  const N = 8, A = () => window.App;
  const halo = cells => { const out = new Set(); cells.forEach(x => { const r = Math.floor(x / N), c = x % N;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) { const rr = r + dr, cc = c + dc; if (rr >= 0 && rr < N && cc >= 0 && cc < N) out.add(rr * N + cc); } }); return out; };
  function randomFleet(sizes) {
    for (let t = 0; t < 500; t++) { const ships = [], busy = new Set(); let ok = true;
      for (const size of sizes) { let placed = false;
        for (let k = 0; k < 300 && !placed; k++) { const h = Math.random() < .5, r = Math.floor(Math.random() * (N - (h ? 0 : size - 1))), c = Math.floor(Math.random() * (N - (h ? size - 1 : 0)));
          const cells = [...Array(size)].map((_, i) => h ? r * N + c + i : (r + i) * N + c);
          if (!cells.some(x => busy.has(x))) { ships.push(cells); halo(cells).forEach(x => busy.add(x)); placed = true; } }
        if (!placed) { ok = false; break; } }
      if (ok) return ships; }
    return []; }
  function editor(gid, ships, sizes, card) {
    let horiz = true, pick = null;
    const md = A().modal('Расставьте корабли', `<div class="sea-ed">
      <div class="sea-grid" style="--n:${N}">${[...Array(N * N)].map((_, i) => `<button type="button" data-i="${i}" aria-label="${Math.floor(i / N) + 1}:${i % N + 1}"></button>`).join('')}</div>
      <div class="sea-pal"></div>
      <div class="sea-tools"><button type="button" class="btn soft sm" data-t="rot">↻ Повернуть</button><button type="button" class="btn soft sm" data-t="rnd">🎲 Случайно</button><button type="button" class="btn ghost sm" data-t="clr">Очистить</button></div>
      <p class="tiny muted center" id="sea-hint"></p>
      <button type="button" class="btn" data-t="go" style="width:100%">Готово — в бой!</button></div>`);
    const grid = md.querySelector('.sea-grid'), pal = md.querySelector('.sea-pal'), hint = md.querySelector('#sea-hint'), go = md.querySelector('[data-t=go]');
    const left = () => { const used = ships.map(s => s.length).sort(), rest = [...sizes]; used.forEach(u => rest.splice(rest.indexOf(u), 1)); return rest; };
    function draw() {
      const own = new Map(); ships.forEach((s, k) => s.forEach(x => own.set(x, k)));
      grid.querySelectorAll('button').forEach(b => { const i = +b.dataset.i; b.className = own.has(i) ? 'ship' : ''; });
      const rest = left(); if (pick && !rest.includes(pick)) pick = null; if (!pick && rest.length) pick = Math.max(...rest);
      pal.innerHTML = rest.length ? [...new Set(rest)].sort((a, b) => b - a).map(z => `<button type="button" class="${z === pick ? 'on' : ''}" data-z="${z}">${'<i></i>'.repeat(z)}<span>×${rest.filter(q => q === z).length}</span></button>`).join('') : '<b class="small">Весь флот на месте 👍</b>';
      hint.textContent = rest.length ? `Выберите корабль и нажмите клетку. Сейчас ставим ${horiz ? 'вправо →' : 'вниз ↓'}` : 'Нажмите на корабль, чтобы убрать его';
      go.disabled = !!rest.length;
    }
    pal.addEventListener('click', e => { const b = e.target.closest('[data-z]'); if (b) { pick = +b.dataset.z; draw(); } });
    grid.addEventListener('click', e => {
      const b = e.target.closest('[data-i]'); if (!b) return; const i = +b.dataset.i;
      const k = ships.findIndex(s => s.includes(i)); if (k >= 0) { pick = ships[k].length; ships.splice(k, 1); draw(); return; }
      if (!pick) return; const r = Math.floor(i / N), c = i % N;
      if ((horiz ? c : r) + pick > N) { hint.textContent = 'Не помещается — выберите клетку ближе к ' + (horiz ? 'левому краю' : 'верху'); return; }
      const cells = [...Array(pick)].map((_, q) => horiz ? i + q : i + q * N), busy = new Set(); ships.forEach(s => halo(s).forEach(x => busy.add(x)));
      if (cells.some(x => busy.has(x))) { hint.textContent = 'Корабли не должны касаться друг друга, даже углами'; return; }
      ships.push(cells); draw(); });
    md.querySelector('[data-t=rot]').onclick = () => { horiz = !horiz; draw(); };
    md.querySelector('[data-t=rnd]').onclick = () => { ships = randomFleet(sizes); draw(); };
    md.querySelector('[data-t=clr]').onclick = () => { ships = []; draw(); };
    go.onclick = async () => { go.disabled = true;
      try { await A().api(`/v3/game/${gid}/sea/place`, { ships, ready: 1 }); md.classList.remove('open'); window.toast && toast('Флот готов! ⚓'); }
      catch (e) { go.disabled = false; }
      card && card.dispatchEvent(new Event('v3refresh', { bubbles: true })); };
    draw();
  }
  document.addEventListener('click', async e => {
    const ed = e.target.closest('[data-v3-seaedit]');
    if (ed) { let ships = []; try { ships = JSON.parse(ed.dataset.ships || '[]'); } catch (x) {} editor(ed.dataset.v3Seaedit, ships, ed.dataset.sizes.split(',').map(Number), ed.closest('.v3-card')); return; }
    const rd = e.target.closest('[data-v3-seaready]');
    if (rd) { rd.disabled = true; try { await A().api(`/v3/game/${rd.dataset.v3Seaready}/sea/place`, { ready: 1 }); window.toast && toast('Флот готов! ⚓'); } catch (x) { rd.disabled = false; }
      rd.dispatchEvent(new Event('v3refresh', { bubbles: true })); }
  });
})();
