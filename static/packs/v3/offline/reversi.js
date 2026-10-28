/* Реверси: фишка переворачивает все фишки соперника, зажатые между ней и вашей по прямой.
   Нет хода — пропуск, ходов нет ни у кого — подсчёт. Бот: альфа-бета по таблице ценности клеток
   (углы ценнее всего, клетки рядом с пустым углом — опасны) плюс подвижность; глубина 1 / 3 / 4. */
(function (OG) {
  'use strict';
  const DIRS = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
  const WEIGHT = [
    100, -20, 10, 5, 5, 10, -20, 100,
    -20, -50, -2, -2, -2, -2, -50, -20,
    10, -2, 1, 1, 1, 1, -2, 10,
    5, -2, 1, 0, 0, 1, -2, 5,
    5, -2, 1, 0, 0, 1, -2, 5,
    10, -2, 1, 1, 1, 1, -2, 10,
    -20, -50, -2, -2, -2, -2, -50, -20,
    100, -20, 10, 5, 5, 10, -20, 100];
  function initial() { const b = new Array(64).fill(0); b[27] = b[36] = -1; b[28] = b[35] = 1; return b; }
  function flips(b, i, me) {
    if (b[i]) return [];
    const r = Math.floor(i / 8), c = i % 8, out = [];
    for (const [dr, dc] of DIRS) {
      const line = [];
      let rr = r + dr, cc = c + dc;
      while (rr >= 0 && rr < 8 && cc >= 0 && cc < 8 && b[rr * 8 + cc] === -me) { line.push(rr * 8 + cc); rr += dr; cc += dc; }
      if (line.length && rr >= 0 && rr < 8 && cc >= 0 && cc < 8 && b[rr * 8 + cc] === me) out.push(...line);
    }
    return out;
  }
  function moves(b, me) { const out = []; for (let i = 0; i < 64; i++) if (!b[i] && flips(b, i, me).length) out.push(i); return out; }
  function play(b, i, me) { const nb = b.slice(); flips(b, i, me).forEach(x => { nb[x] = me; }); nb[i] = me; return nb; }
  function evaluate(b, me) {
    let s = 0, n = 0;
    for (let i = 0; i < 64; i++) {
      if (!b[i]) continue;
      n++;
      let w = WEIGHT[i];
      // рядом с занятым углом клетка уже не опасна
      if (w < 0 && [[1, 8, 9, 0], [6, 15, 14, 7], [48, 57, 49, 56], [55, 62, 54, 63]].some(([a, b2, c2, corner]) => [a, b2, c2].includes(i) && b[corner])) w = 4;
      s += b[i] === me ? w : -w;
    }
    const mob = moves(b, me).length - moves(b, -me).length;
    return s + mob * (n < 48 ? 6 : 2);
  }
  function search(b, me, depth, alpha, beta, passed) {
    const ms = moves(b, me);
    if (!ms.length) {
      if (passed) { let d = 0; b.forEach(v => { d += v === me ? 1 : v ? -1 : 0; }); return d * 1000; }  // конец игры
      return -search(b, -me, depth, -beta, -alpha, true);
    }
    if (depth === 0) return evaluate(b, me);
    let best = -Infinity;
    ms.sort((x, y) => WEIGHT[y] - WEIGHT[x]);
    for (const i of ms) {
      const v = -search(play(b, i, me), -me, depth - 1, -beta, -alpha, false);
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  }
  const DEPTH = { easy: 1, mid: 3, hard: 4 };
  function bestMove(b, me, level) {
    const ms = moves(b, me);
    if (level === 'easy' && Math.random() < .35) return OG.pick(ms);
    let best = -Infinity, pick = [];
    for (const i of ms) {
      const v = -search(play(b, i, me), -me, (DEPTH[level] || 3) - 1, -Infinity, Infinity, false);
      if (v > best) { best = v; pick = [i]; } else if (v === best) pick.push(i);
    }
    return OG.pick(pick);
  }

  OG.add({
    id: 'reversi', title: 'Реверси', icon: 'contrast', desc: 'Зажимайте и переворачивайте фишки соперника', modes: ['bot', 'duo'],
    opts: [{ key: 'level', bot: true, def: 'mid', items: [['easy', 'Легко'], ['mid', 'Средне'], ['hard', 'Сложно']] }],
    ai: { initial, moves, play, bestMove },
    start(ctx) {
      let b = initial(), me = 1, last = -1, busy = false, flipped = [];
      const human = ctx.round % 2 ? -1 : 1;  // чёрные (1) ходят первыми
      const nameOf = s => (ctx.mode === 'bot' ? (s === human ? 'Вы' : 'Бот') : ctx.names[s > 0 ? 0 : 1]);
      const bot = () => ctx.mode === 'bot' && me !== human;
      ctx.box.innerHTML = `<div class="og-rev-score"></div><div class="og-board og-rev" style="--n:8">${b.map((_, i) => `<button type="button" data-i="${i}" aria-label="${Math.floor(i / 8) + 1}:${i % 8 + 1}"></button>`).join('')}</div>`;
      const cells = [...ctx.box.querySelectorAll('[data-i]')], sc = ctx.box.querySelector('.og-rev-score');
      const count = s => b.filter(v => v === s).length;
      const draw = () => {
        const ms = new Set(busy || bot() ? [] : moves(b, me));
        cells.forEach((c, i) => {
          c.innerHTML = b[i] ? `<span class="pc ${b[i] > 0 ? 'k' : 'w'}${flipped.includes(i) ? ' flip' : ''}"></span>` : '';
          c.disabled = !ms.has(i); c.classList.toggle('hint', ms.has(i)); c.classList.toggle('last', i === last);
        });
        sc.innerHTML = `<span><span class="pc k"></span> ${OG.esc(nameOf(1))}: <b>${count(1)}</b></span><span><span class="pc w"></span> ${OG.esc(nameOf(-1))}: <b>${count(-1)}</b></span>`;
      };
      const put = i => { flipped = flips(b, i, me); b = play(b, i, me); last = i; me = -me; next(false); };
      const next = passed => {
        if (!moves(b, me).length) {
          if (!moves(b, -me).length) {  // ходов нет ни у кого
            busy = true; draw();
            const d = count(1) - count(-1);
            if (!d) { ctx.over(`Ничья ${count(1)} : ${count(-1)}`, -1); return; }
            const w = d > 0 ? 1 : -1, p = ctx.mode === 'bot' ? (w === human ? 0 : 1) : (w > 0 ? 0 : 1);
            ctx.over(`${ctx.mode === 'bot' ? (w === human ? 'Вы победили' : 'Бот победил') : 'Победил ' + OG.esc(nameOf(w))} — ${count(1)} : ${count(-1)}`, p);
            return;
          }
          const msg = ctx.mode === 'bot' ? (me === human ? 'У вас нет ходов — пропуск.' : 'У бота нет ходов — пропуск.') : `${OG.esc(nameOf(me))}: ходов нет — пропуск.`;
          me = -me;
          next(true);
          ctx.status(msg + ' ' + (bot() ? 'Бот думает…' : ctx.mode === 'bot' ? 'Снова ваш ход' : `Ходит ${OG.esc(nameOf(me))}`));
          return;
        }
        if (bot()) { if (!passed) ctx.status('Бот думает…'); draw(); ctx.later(() => put(bestMove(b, me, ctx.opt.level)), 450); }
        else { ctx.status(ctx.mode === 'bot' ? `Ваш ход — ${me > 0 ? 'чёрные' : 'белые'}` : `Ходит ${OG.esc(nameOf(me))} — ${me > 0 ? 'чёрные' : 'белые'}`); draw(); }
      };
      ctx.box.addEventListener('click', e => { const c = e.target.closest('[data-i]'); if (c && !c.disabled && !busy && !bot()) put(+c.dataset.i); });
      next(false);
    },
  });
})(window.OG);
