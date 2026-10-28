/* Сапёр: первая клетка всегда пустая (мины расставляются после первого нажатия), цифра — сколько мин рядом.
   Флажок — переключателем «Флажок» или долгим нажатием; нажатие на открытую цифру с нужным числом флажков открывает соседей. */
(function (OG) {
  'use strict';
  const LEVELS = { easy: [9, 9, 10], mid: [12, 12, 24], hard: [12, 16, 40] };  // столбцы, ряды, мины
  function around(w, h, i) {
    const r = Math.floor(i / w), c = i % w, out = [];
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const rr = r + dr, cc = c + dc;
      if ((dr || dc) && rr >= 0 && rr < h && cc >= 0 && cc < w) out.push(rr * w + cc);
    }
    return out;
  }
  function lay(w, h, n, safe) {  // мины везде, кроме первой клетки и её соседей
    const ban = new Set([safe, ...around(w, h, safe)]);
    const free = [...Array(w * h).keys()].filter(i => !ban.has(i));
    return new Set(OG.shuffle(free).slice(0, n));
  }

  OG.add({
    id: 'mines', title: 'Сапёр', icon: 'flag', desc: 'Откройте поле и не попадите на мину', modes: ['solo'],
    opts: [{ key: 'level', def: 'easy', items: [['easy', '9×9'], ['mid', '12×12'], ['hard', '12×16']] }],
    ai: { lay, around },
    start(ctx) {
      const [w, h, n] = LEVELS[ctx.opt.level] || LEVELS.easy;
      let mines = null, open = new Set(), flags = new Set(), flagMode = false, over = false, t0 = 0, timer = 0;
      const near = i => around(w, h, i).filter(j => mines.has(j)).length;
      ctx.box.innerHTML = `<div class="og-row og-mines-bar"><span class="chip" data-left>${OG.icon('flag')} ${n}</span><span class="chip" data-time>${OG.icon('clock')} 0</span>`
        + `<button type="button" class="chip" data-flag aria-pressed="false">${OG.icon('flag')} Флажок</button></div>`
        + `<div class="og-board og-mines" style="--n:${w}">${Array.from({ length: w * h }, (_, i) => `<button type="button" data-i="${i}" aria-label="${Math.floor(i / w) + 1}:${i % w + 1}"></button>`).join('')}</div>`;
      const cells = [...ctx.box.querySelectorAll('[data-i]')], flagBtn = ctx.box.querySelector('[data-flag]');
      const tick = () => { if (!over && t0) { ctx.box.querySelector('[data-time]').innerHTML = `${OG.icon('clock')} ${Math.floor((Date.now() - t0) / 1000)}`; timer = ctx.later(tick, 1000); } };
      const draw = boom => {
        cells.forEach((c, i) => {
          const isOpen = open.has(i), m = mines && mines.has(i);
          let cls = isOpen ? 'op' : '', html = '';
          if (isOpen) { const k = near(i); if (k) { html = k; cls += ' n' + k; } }
          else if (flags.has(i)) { html = OG.icon('flag'); cls = 'fl' + (over && !m ? ' bad' : ''); }
          if (over && m && !flags.has(i)) { cls = 'op mine' + (i === boom ? ' boom' : ''); html = '<i></i>'; }
          c.className = cls; c.innerHTML = html;
        });
        ctx.box.querySelector('[data-left]').innerHTML = `${OG.icon('flag')} ${n - flags.size}`;
      };
      const reveal = i => {  // открываем клетку, а пустые — волной
        const stack = [i];
        while (stack.length) {
          const x = stack.pop();
          if (open.has(x) || flags.has(x)) continue;
          open.add(x);
          if (!near(x)) around(w, h, x).forEach(j => { if (!open.has(j)) stack.push(j); });
        }
      };
      const lose = i => { over = true; draw(i); ctx.over('Мина! Попробуйте ещё раз', 1); };
      const check = () => {
        if (open.size === w * h - n) {
          over = true; mines.forEach(m => flags.add(m)); draw();
          const sec = Math.floor((Date.now() - t0) / 1000), key = 'best:mines:' + ctx.opt.level, best = OG.store.get(key, 0);
          if (!best || sec < best) OG.store.set(key, sec);
          ctx.over(`Поле разминировано за ${sec} с${best && sec >= best ? ` (рекорд ${best} с)` : ' — новый рекорд!'}`, 0);
        }
      };
      const tap = (i, flag) => {
        if (over) return;
        if (flag) {
          if (open.has(i)) return;
          if (flags.has(i)) flags.delete(i); else flags.add(i);
          draw(); return;
        }
        if (flags.has(i)) return;
        if (!mines) { mines = lay(w, h, n, i); t0 = Date.now(); tick(); }
        if (open.has(i)) {  // «аккорд»: флажков вокруг столько же, сколько мин — открываем остальных соседей
          const nb = around(w, h, i);
          if (near(i) && nb.filter(j => flags.has(j)).length === near(i)) {
            const hit = nb.find(j => !flags.has(j) && mines.has(j));
            if (hit !== undefined) { lose(hit); return; }
            nb.forEach(j => { if (!flags.has(j)) reveal(j); });
          }
        } else if (mines.has(i)) { lose(i); return; } else reveal(i);
        draw(); check();
      };
      let press = null, longFired = false;
      const board = ctx.box.querySelector('.og-mines');
      board.addEventListener('pointerdown', e => {
        const c = e.target.closest('[data-i]'); if (!c) return;
        longFired = false; clearTimeout(press);
        press = setTimeout(() => { longFired = true; tap(+c.dataset.i, true); if (navigator.vibrate) navigator.vibrate(20); }, 420);
      });
      ['pointerup', 'pointerleave', 'pointercancel'].forEach(t => board.addEventListener(t, () => clearTimeout(press)));
      board.addEventListener('contextmenu', e => e.preventDefault());
      board.addEventListener('click', e => { const c = e.target.closest('[data-i]'); if (!c) return; if (longFired) { longFired = false; return; } tap(+c.dataset.i, flagMode); });
      flagBtn.onclick = () => { flagMode = !flagMode; flagBtn.classList.toggle('active', flagMode); flagBtn.setAttribute('aria-pressed', flagMode); };
      ctx.cleanup = () => { clearTimeout(press); clearTimeout(timer); };
      ctx.status(`Мин: ${n}. Первая клетка всегда безопасна`);
      draw();
    },
  });
})(window.OG);
