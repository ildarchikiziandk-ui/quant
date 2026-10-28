/* Крестики-нолики: 3×3 (три в ряд) и 5×5 (четыре в ряд). Бот 3×3 — полный минимакс (непобедим),
   5×5 — альфа-бета на 4 хода вперёд с оценкой открытых линий. «Полегче» иногда ходит наугад. */
(function (OG) {
  'use strict';
  const cache = {};
  function lines(n, k) {  // все отрезки длины k: горизонтали, вертикали, диагонали
    const key = n + ':' + k;
    if (cache[key]) return cache[key];
    const out = [];
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
      for (const [dr, dc] of [[0, 1], [1, 0], [1, 1], [1, -1]]) {
        const er = r + dr * (k - 1), ec = c + dc * (k - 1);
        if (er < 0 || er >= n || ec < 0 || ec >= n) continue;
        out.push(Array.from({ length: k }, (_, i) => (r + dr * i) * n + c + dc * i));
      }
    }
    return (cache[key] = out);
  }
  function winner(b, n, k) {
    for (const l of lines(n, k)) { const v = b[l[0]]; if (v && l.every(i => b[i] === v)) return { v, line: l }; }
    return null;
  }
  const W = [0, 1, 6, 40, 300];  // цена линии, где только мои знаки (1, 2, 3, 4 знака)
  function evaluate(b, n, k, me) {
    let s = 0;
    for (const l of lines(n, k)) {
      let a = 0, o = 0;
      for (const i of l) { if (b[i] === me) a++; else if (b[i]) o++; }
      if (a && !o) s += W[a]; else if (o && !a) s -= W[o] * 1.2;
    }
    return s;
  }
  function moves(b, n) {  // на большом поле — только клетки рядом с уже занятыми
    const empty = [];
    b.forEach((v, i) => { if (!v) empty.push(i); });
    if (n === 3 || empty.length === b.length) return n === 3 ? empty : [Math.floor(b.length / 2)];
    return empty.filter(i => {
      const r = Math.floor(i / n), c = i % n;
      for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
        const rr = r + dr, cc = c + dc;
        if ((dr || dc) && rr >= 0 && rr < n && cc >= 0 && cc < n && b[rr * n + cc]) return true;
      }
      return false;
    });
  }
  // negamax с альфа-бета отсечением: оценка позиции для того, кто ходит (me)
  function search(b, n, k, me, depth, alpha, beta, ply) {
    const opp = me === 'x' ? 'o' : 'x';
    const ms = moves(b, n);
    if (!ms.length) return 0;
    if (depth === 0) return evaluate(b, n, k, me);
    let best = -Infinity;
    for (const i of ms) {
      b[i] = me;
      const v = winner(b, n, k) ? 10000 - ply : -search(b, n, k, opp, depth - 1, -beta, -alpha, ply + 1);
      b[i] = '';
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  }
  function bestMove(b, n, k, me, level) {
    const ms = moves(b, n);
    if (level === 'easy' && Math.random() < (n === 3 ? .45 : .3)) return OG.pick(ms);
    const depth = n === 3 ? 9 : level === 'easy' ? 2 : 4;
    let best = -Infinity, pick = [];
    for (const i of ms) {
      b[i] = me;
      const v = winner(b, n, k) ? 10000 : -search(b, n, k, me === 'x' ? 'o' : 'x', depth - 1, -Infinity, Infinity, 1);
      b[i] = '';
      if (v > best) { best = v; pick = [i]; } else if (v === best) pick.push(i);
    }
    return OG.pick(pick);  // из равных ходов — любой, чтобы партии не повторялись
  }

  const MARK = { x: '<svg viewBox="0 0 24 24" class="og-x"><path d="M6 6l12 12M18 6L6 18"/></svg>', o: '<svg viewBox="0 0 24 24" class="og-o"><circle cx="12" cy="12" r="7"/></svg>' };

  OG.add({
    id: 'ttt', title: 'Крестики-нолики', icon: 'x', desc: '3×3 или 5×5 до четырёх в ряд', modes: ['bot', 'duo'],
    opts: [{ key: 'size', items: [['3', '3×3'], ['5', '5×5']] },
           { key: 'level', bot: true, def: 'hard', items: [['easy', 'Полегче'], ['hard', 'Непобедимый']] }],
    ai: { winner, bestMove, lines },
    start(ctx) {
      const n = +ctx.opt.size, k = n === 3 ? 3 : 4, b = Array(n * n).fill('');
      const first = ctx.round % 2;  // кто ходит крестиками: партии чередуются
      const symOf = p => (p === first ? 'x' : 'o'), playerOf = s => (s === symOf(0) ? 0 : 1);
      let turn = 'x', busy = false;
      ctx.box.innerHTML = `<div class="og-board og-ttt-b" style="--n:${n}">${b.map((_, i) => `<button type="button" data-i="${i}" aria-label="${Math.floor(i / n) + 1}:${i % n + 1}"></button>`).join('')}</div>`;
      const cells = [...ctx.box.querySelectorAll('[data-i]')];
      const bot = () => ctx.mode === 'bot' && playerOf(turn) === 1;
      const draw = (win) => cells.forEach((c, i) => { c.innerHTML = b[i] ? MARK[b[i]] : ''; c.disabled = !!b[i] || busy || bot() || !!win; c.classList.toggle('win', !!win && win.line.includes(i)); });
      const put = i => {
        b[i] = turn;
        const w = winner(b, n, k);
        if (w) { busy = true; draw(w); const p = playerOf(w.v); ctx.over(ctx.mode === 'bot' ? (p === 0 ? 'Вы победили!' : 'Бот победил') : `Победил ${ctx.names[p]}`, p); return; }
        if (b.every(Boolean)) { busy = true; draw(); ctx.over('Ничья', -1); return; }
        turn = turn === 'x' ? 'o' : 'x';
        next();
      };
      const next = () => {
        const p = playerOf(turn), mark = turn === 'x' ? '✕' : '○';
        if (bot()) {
          ctx.status('Бот думает…'); draw();
          ctx.later(() => put(bestMove(b, n, k, turn, ctx.opt.level)), 380);
        } else {
          ctx.status(ctx.mode === 'bot' ? `Ваш ход: ${mark}` : `Ходит ${ctx.names[p]}: ${mark}`); draw();
        }
      };
      ctx.box.addEventListener('click', e => { const c = e.target.closest('[data-i]'); if (c && !c.disabled) put(+c.dataset.i); });
      next();
    },
  });
})(window.OG);
