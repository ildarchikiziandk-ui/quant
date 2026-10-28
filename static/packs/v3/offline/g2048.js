/* 2048 без сети: рекорд хранится на этом устройстве (в разделе «Игры» есть онлайн-версия с рекордами друзей). */
(function (OG) {
  'use strict';
  function slide(row) {  // сдвиг строки влево со слиянием; возвращает [новая строка, очки]
    const a = row.filter(Boolean);
    let pts = 0;
    for (let i = 0; i < a.length - 1; i++) if (a[i] === a[i + 1]) { a[i] *= 2; pts += a[i]; a.splice(i + 1, 1); }
    while (a.length < row.length) a.push(0);
    return [a, pts];
  }
  function move(grid, dir) {  // grid 4×4, dir L/R/U/D → [новое поле, очки, сдвинулось ли]
    const g = grid.map(r => r.slice());
    let pts = 0;
    for (let i = 0; i < 4; i++) {
      let line = dir === 'L' || dir === 'R' ? g[i].slice() : g.map(r => r[i]);
      if (dir === 'R' || dir === 'D') line.reverse();
      const [res, p] = slide(line);
      pts += p;
      if (dir === 'R' || dir === 'D') res.reverse();
      if (dir === 'L' || dir === 'R') g[i] = res; else res.forEach((v, y) => { g[y][i] = v; });
    }
    return [g, pts, JSON.stringify(g) !== JSON.stringify(grid)];
  }
  const canMove = g => ['L', 'R', 'U', 'D'].some(d => move(g, d)[2]);

  OG.add({
    id: 'g2048', title: '2048', icon: 'grid', desc: 'Соединяйте плитки и дойдите до 2048', modes: ['solo'],
    ai: { slide, move, canMove },
    start(ctx) {
      let grid = [...Array(4)].map(() => [0, 0, 0, 0]), score = 0, best = OG.store.get('best:2048', 0), over = false;
      const spawn = () => {
        const e = [];
        grid.forEach((r, y) => r.forEach((v, x) => { if (!v) e.push([y, x]); }));
        if (!e.length) return null;
        const [y, x] = OG.pick(e);
        grid[y][x] = Math.random() < .9 ? 2 : 4;
        return [y, x];
      };
      const saved = OG.store.get('2048', null);
      if (saved && saved.grid && !ctx.round) { grid = saved.grid; score = saved.score; } else { spawn(); spawn(); }
      ctx.box.innerHTML = '<div class="og-row og-scores"><div class="v3-gscore"><span>Счёт</span><b data-s>0</b></div><div class="v3-gscore"><span>Рекорд</span><b data-b>0</b></div></div><div class="v3-g2048"></div><p class="tiny faint center mt">Смахивайте пальцем или нажимайте стрелки.</p>';
      const board = ctx.box.querySelector('.v3-g2048');
      const draw = born => {
        board.innerHTML = grid.map((r, y) => r.map((v, x) => `<div class="t${v ? ' v' + Math.min(v, 4096) : ''}${born && born[0] === y && born[1] === x ? ' born' : ''}">${v || ''}</div>`).join('')).join('');
        best = Math.max(best, score);
        ctx.box.querySelector('[data-s]').textContent = score; ctx.box.querySelector('[data-b]').textContent = best;
        OG.store.set('best:2048', best); OG.store.set('2048', over ? null : { grid, score });
      };
      const go = dir => {
        if (over) return;
        const [g, pts, moved] = move(grid, dir);
        if (!moved) return;
        grid = g; score += pts;
        const born = spawn();
        if (!canMove(grid)) over = true;
        draw(born);
        if (over) ctx.over(`Ходов нет. Счёт: ${score}`, score >= best && score > 0 ? 0 : null);
        else if (grid.some(r => r.includes(2048)) && !ctx.won) { ctx.won = true; ctx.status('<b>2048!</b> Можно играть дальше'); OG.confetti(); }
      };
      ctx.swipe(board, go);
      ctx.key(e => { const d = { ArrowLeft: 'L', ArrowRight: 'R', ArrowUp: 'U', ArrowDown: 'D' }[e.key]; if (d) { e.preventDefault(); go(d); } });
      ctx.status('Одинаковые плитки складываются');
      draw();
    },
  });
})(window.OG);
