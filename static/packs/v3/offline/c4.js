/* Четыре в ряд: поле 7×6, фишка падает вниз. Бот — negamax с альфа-бета отсечением
   (глубина 2 / 5 / 7 полуходов) и оценкой всех «окон» из четырёх клеток; центр важнее краёв. */
(function (OG) {
  'use strict';
  const C = 7, R = 6, ORDER = [3, 2, 4, 1, 5, 0, 6];
  const WIN = [];  // все окна по 4 клетки (индекс = ряд * 7 + столбец, ряд 0 — верхний)
  for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
    for (const [dr, dc] of [[0, 1], [1, 0], [1, 1], [1, -1]]) {
      const er = r + dr * 3, ec = c + dc * 3;
      if (er >= 0 && er < R && ec >= 0 && ec < C) WIN.push([0, 1, 2, 3].map(i => (r + dr * i) * C + c + dc * i));
    }
  }
  const BY_CELL = Array.from({ length: R * C }, (_, i) => WIN.filter(w => w.includes(i)));
  const top = (b, c) => { for (let r = R - 1; r >= 0; r--) if (!b[r * C + c]) return r * C + c; return -1; };
  const wins = (b, i) => BY_CELL[i].some(w => w.every(j => b[j] === b[i]));
  const winLine = (b, i) => BY_CELL[i].find(w => w.every(j => b[j] === b[i]));
  const SCORE = [0, 1, 4, 24];
  function evaluate(b, me) {
    let s = 0;
    for (let r = 0; r < R; r++) { if (b[r * C + 3] === me) s += 3; else if (b[r * C + 3]) s -= 3; }
    for (const w of WIN) {
      let a = 0, o = 0;
      for (const j of w) { if (b[j] === me) a++; else if (b[j]) o++; }
      if (a && !o) s += SCORE[a]; else if (o && !a) s -= SCORE[o];
    }
    return s;
  }
  function search(b, me, depth, alpha, beta, left) {
    if (!left) return 0;  // поле заполнено — ничья
    if (depth === 0) return evaluate(b, me);
    const opp = 3 - me;
    let best = -Infinity;
    for (const c of ORDER) {
      const i = top(b, c);
      if (i < 0) continue;
      b[i] = me;
      const v = wins(b, i) ? 1000 + depth : -search(b, opp, depth - 1, -beta, -alpha, left - 1);
      b[i] = 0;
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  }
  const DEPTH = { easy: 2, mid: 5, hard: 7 };
  function bestMove(b, me, level) {
    const cols = ORDER.filter(c => top(b, c) >= 0), left = b.filter(v => !v).length;
    if (level === 'easy' && Math.random() < .25) return OG.pick(cols);
    const depth = DEPTH[level] || 5;
    let best = -Infinity, pick = [];
    for (const c of cols) {
      const i = top(b, c);
      b[i] = me;
      const v = wins(b, i) ? 100000 : -search(b, 3 - me, depth - 1, -Infinity, Infinity, left - 1);
      b[i] = 0;
      if (v > best) { best = v; pick = [c]; } else if (v === best) pick.push(c);
    }
    return pick[0] === 3 || pick.length === 1 ? pick[0] : OG.pick(pick);
  }

  OG.add({
    id: 'c4', title: 'Четыре в ряд', icon: 'layers', desc: 'Фишки падают вниз — соберите четыре подряд', modes: ['bot', 'duo'],
    opts: [{ key: 'level', bot: true, def: 'mid', items: [['easy', 'Легко'], ['mid', 'Средне'], ['hard', 'Сложно']] }],
    ai: { bestMove, wins, top, C, R },
    start(ctx) {
      const b = new Int8Array(C * R), first = ctx.round % 2;  // first — кто ходит первым (синие фишки)
      const colorOf = p => (p === first ? 1 : 2), playerOf = v => (v === colorOf(0) ? 0 : 1);
      let turn = 1, busy = false, last = -1, line = null;
      ctx.box.innerHTML = `<div class="v3-c4 og-c4b" style="--cols:${C}">${Array.from({ length: C }, (_, c) => `<button type="button" class="v3-c4-col" data-c="${c}" aria-label="Столбец ${c + 1}">${Array.from({ length: R }, (_, r) => `<i data-i="${r * C + c}"></i>`).join('')}</button>`).join('')}</div>`;
      const cols = [...ctx.box.querySelectorAll('[data-c]')], dots = [...ctx.box.querySelectorAll('[data-i]')];
      const bot = () => ctx.mode === 'bot' && playerOf(turn) === 1;
      const draw = () => {
        dots.forEach(d => { const i = +d.dataset.i; d.className = (b[i] === 1 ? 'r' : b[i] === 2 ? 'y' : '') + (i === last ? ' last' : '') + (line && line.includes(i) ? ' win' : ''); });
        cols.forEach((col, c) => { col.disabled = busy || bot() || top(b, c) < 0; });
      };
      const drop = c => {
        const i = top(b, c);
        if (i < 0) return;
        b[i] = turn; last = i;
        if (wins(b, i)) {
          busy = true; line = winLine(b, i); draw();
          const p = playerOf(turn);
          ctx.over(ctx.mode === 'bot' ? (p === 0 ? 'Вы победили!' : 'Бот победил') : `Победил ${ctx.names[p]}`, p); return;
        }
        if (b.every(Boolean)) { busy = true; draw(); ctx.over('Ничья', -1); return; }
        turn = 3 - turn;
        next();
      };
      const dot = v => `<i class="v3-dot ${v === 1 ? 'r' : 'y'}"></i>`;
      const next = () => {
        if (bot()) { ctx.status(`${dot(turn)} Бот думает…`); draw(); ctx.later(() => drop(bestMove(b, turn, ctx.opt.level)), 300); }
        else { ctx.status(ctx.mode === 'bot' ? `${dot(turn)} Ваш ход — нажмите на столбец` : `${dot(turn)} Ходит ${ctx.names[playerOf(turn)]}`); draw(); }
      };
      ctx.box.addEventListener('click', e => { const col = e.target.closest('[data-c]'); if (col && !col.disabled) drop(+col.dataset.c); });
      ctx.key(e => { const c = +e.key - 1; if (c >= 0 && c < C && !cols[c].disabled) drop(c); });
      next();
    },
  });
})(window.OG);
