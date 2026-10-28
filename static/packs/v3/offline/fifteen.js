/* Пятнашки 3×3 и 4×4: перемешиваем случайными ходами из собранного положения — так задача всегда решаема.
   Нажатие на плитку в одном ряду или столбце с пустой клеткой сдвигает сразу несколько плиток. */
(function (OG) {
  'use strict';
  function shuffle(n) {
    const b = [...Array(n * n).keys()].map(i => (i + 1) % (n * n));  // 1, 2, … , 0 (0 — пустая)
    let e = n * n - 1, prev = -1;
    for (let k = 0; k < n * n * 40; k++) {
      const r = Math.floor(e / n), c = e % n, opts = [];
      if (r > 0) opts.push(e - n); if (r < n - 1) opts.push(e + n); if (c > 0) opts.push(e - 1); if (c < n - 1) opts.push(e + 1);
      const to = OG.pick(opts.filter(x => x !== prev));
      b[e] = b[to]; b[to] = 0; prev = e; e = to;
    }
    return solved(b) ? shuffle(n) : b;
  }
  const solved = b => b.every((v, i) => v === (i + 1) % b.length);
  function slide(b, n, i) {  // сдвинуть плитки от i к пустой клетке; false — не в одном ряду/столбце
    const e = b.indexOf(0);
    if (i === e) return false;
    const same = Math.floor(i / n) === Math.floor(e / n), step = same ? (i > e ? 1 : -1) : i % n === e % n ? (i > e ? n : -n) : 0;
    if (!step) return false;
    for (let x = e; x !== i; x += step) b[x] = b[x + step];
    b[i] = 0;
    return true;
  }

  OG.add({
    id: 'fifteen', title: 'Пятнашки', icon: 'shuffle', desc: 'Расставьте плитки по порядку', modes: ['solo'],
    opts: [{ key: 'size', def: '4', items: [['3', '3×3'], ['4', '4×4']] }],
    ai: { shuffle, slide, solved },
    start(ctx) {
      const n = +ctx.opt.size, b = shuffle(n), key = 'best:15:' + n;
      let movesN = 0, done = false;
      ctx.box.innerHTML = `<div class="og-board og-15" style="--n:${n}">${b.map((_, i) => `<button type="button" data-i="${i}"></button>`).join('')}</div>`;
      const cells = [...ctx.box.querySelectorAll('[data-i]')];
      const draw = () => {
        cells.forEach((c, i) => { c.textContent = b[i] || ''; c.className = b[i] ? (b[i] === i + 1 ? 'ok' : '') : 'empty'; });
        const best = OG.store.get(key, 0);
        if (!done) ctx.status(`Ходов: ${movesN}${best ? ` · рекорд ${best}` : ''}`);
      };
      const tap = i => {
        if (done || !slide(b, n, i)) return;
        movesN++;
        if (solved(b)) {
          done = true; draw();
          const best = OG.store.get(key, 0), rec = !best || movesN < best;
          if (rec) OG.store.set(key, movesN);
          ctx.over(`Собрано за ${movesN} ходов${rec ? ' — новый рекорд!' : ''}`, 0);
          return;
        }
        draw();
      };
      ctx.box.addEventListener('click', e => { const c = e.target.closest('[data-i]'); if (c) tap(+c.dataset.i); });
      const dirMove = d => {  // смахивание/стрелка двигает плитку рядом с пустой клеткой в эту сторону
        const e = b.indexOf(0), r = Math.floor(e / n), c = e % n;
        const from = { L: c < n - 1 ? e + 1 : -1, R: c > 0 ? e - 1 : -1, U: r < n - 1 ? e + n : -1, D: r > 0 ? e - n : -1 }[d];
        if (from >= 0) tap(from);
      };
      ctx.swipe(ctx.box.querySelector('.og-15'), dirMove);
      ctx.key(e => { const d = { ArrowLeft: 'L', ArrowRight: 'R', ArrowUp: 'U', ArrowDown: 'D' }[e.key]; if (d) { e.preventDefault(); dirMove(d); } });
      draw();
    },
  });
})(window.OG);
