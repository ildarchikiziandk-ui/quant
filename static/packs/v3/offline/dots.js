/* Точки и квадратики: по очереди соединяйте соседние точки; кто замкнул квадрат — забирает его и ходит ещё.
   Бот: забирает готовые квадраты, иначе ставит «безопасную» линию (не третью сторону квадрата),
   а когда безопасных нет — отдаёт самую короткую цепочку. */
(function (OG) {
  'use strict';
  function game(R, C) {  // линии: сначала горизонтальные (R+1)×C, потом вертикальные R×(C+1)
    const H = (R + 1) * C, total = H + R * (C + 1);
    const sides = (r, c) => [r * C + c, (r + 1) * C + c, H + r * (C + 1) + c, H + r * (C + 1) + c + 1];
    const boxesOf = l => {
      const out = [];
      if (l < H) { const r = Math.floor(l / C), c = l % C; if (r > 0) out.push([r - 1, c]); if (r < R) out.push([r, c]); }
      else { const k = l - H, r = Math.floor(k / (C + 1)), c = k % (C + 1); if (c > 0) out.push([r, c - 1]); if (c < C) out.push([r, c]); }
      return out;
    };
    const count = (lines, r, c) => sides(r, c).filter(x => lines[x]).length;
    return { R, C, H, total, sides, boxesOf, count };
  }
  function grabAll(g, lines) {  // сколько квадратов можно забрать подряд (жадно), lines меняется
    let n = 0, found = true;
    while (found) {
      found = false;
      for (let r = 0; r < g.R && !found; r++) for (let c = 0; c < g.C && !found; c++) {
        if (g.count(lines, r, c) === 3) { const l = g.sides(r, c).find(x => !lines[x]); lines[l] = 1; n++; found = true; g.boxesOf(l).forEach(([rr, cc]) => { if (g.count(lines, rr, cc) === 4 && !(rr === r && cc === c)) n++; }); }
      }
    }
    return n;
  }
  function botMove(g, lines, level) {
    const free = [];
    for (let l = 0; l < g.total; l++) if (!lines[l]) free.push(l);
    const closes = free.filter(l => g.boxesOf(l).some(([r, c]) => g.count(lines, r, c) === 3));
    if (closes.length && (level !== 'easy' || Math.random() < .7)) return OG.pick(closes);
    const safe = free.filter(l => g.boxesOf(l).every(([r, c]) => g.count(lines, r, c) < 2));
    if (level === 'easy') return OG.pick(safe.length && Math.random() < .6 ? safe : free);
    if (safe.length) return OG.pick(safe);
    let best = Infinity, pick = [];
    for (const l of free) {  // меньше всего отдаём сопернику
      const t = lines.slice(); t[l] = 1;
      const n = grabAll(g, t);
      if (n < best) { best = n; pick = [l]; } else if (n === best) pick.push(l);
    }
    return OG.pick(pick);
  }

  OG.add({
    id: 'dots', title: 'Точки и квадратики', icon: 'grid', desc: 'Замкнул квадрат — он твой, ходи ещё', modes: ['bot', 'duo'],
    opts: [{ key: 'size', def: '4', items: [['3', '3×3'], ['4', '4×4'], ['5', '5×5']] },
           { key: 'level', bot: true, def: 'hard', items: [['easy', 'Полегче'], ['hard', 'Хитрый']] }],
    ai: { game, botMove, grabAll },
    start(ctx) {
      const n = +ctx.opt.size, g = game(n, n), lines = new Array(g.total).fill(0), owner = new Array(n * n).fill(-1);
      let turn = ctx.round % 2, busy = false, last = -1;
      const S = 56, M = 14, W = n * S + 2 * M;
      const pos = l => {  // концы линии в координатах SVG
        if (l < g.H) { const r = Math.floor(l / n), c = l % n; return [M + c * S, M + r * S, M + (c + 1) * S, M + r * S]; }
        const k = l - g.H, r = Math.floor(k / (n + 1)), c = k % (n + 1);
        return [M + c * S, M + r * S, M + c * S, M + (r + 1) * S];
      };
      let svg = `<svg class="og-dots" viewBox="0 0 ${W} ${W}">`;
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) svg += `<rect data-b="${r * n + c}" x="${M + c * S + 4}" y="${M + r * S + 4}" width="${S - 8}" height="${S - 8}" rx="8"/>`;
      for (let l = 0; l < g.total; l++) { const [x1, y1, x2, y2] = pos(l); svg += `<line class="ln" data-l="${l}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><line class="hit" data-h="${l}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`; }
      for (let r = 0; r <= n; r++) for (let c = 0; c <= n; c++) svg += `<circle cx="${M + c * S}" cy="${M + r * S}" r="5"/>`;
      ctx.box.innerHTML = svg + '</svg>';
      const lineEl = [...ctx.box.querySelectorAll('[data-l]')], boxEl = [...ctx.box.querySelectorAll('[data-b]')];
      const score = p => owner.filter(x => x === p).length;
      const bot = () => ctx.mode === 'bot' && turn === 1;
      const draw = () => {
        lineEl.forEach((el, l) => { el.setAttribute('class', 'ln' + (lines[l] ? ' p' + (lines[l] - 1) : '') + (l === last ? ' last' : '')); });
        boxEl.forEach((el, i) => { el.setAttribute('class', owner[i] >= 0 ? 'p' + owner[i] : ''); });
        ctx.box.classList.toggle('wait', busy || bot());
      };
      const tally = () => `<i class="v3-dot r"></i> ${OG.esc(ctx.names[0])} <b>${score(0)}</b> : <b>${score(1)}</b> ${OG.esc(ctx.names[1])} <i class="v3-dot y"></i>`;
      const put = l => {
        if (lines[l]) return;
        lines[l] = turn + 1; last = l;
        let got = 0;
        g.boxesOf(l).forEach(([r, c]) => { if (g.count(lines, r, c) === 4) { owner[r * n + c] = turn; got++; } });
        if (owner.every(x => x >= 0)) {
          busy = true; draw();
          const a = score(0), b = score(1);
          ctx.over(a === b ? `Ничья ${a} : ${b}` : ctx.mode === 'bot' ? (a > b ? `Вы победили ${a} : ${b}` : `Бот победил ${b} : ${a}`) : `Победил ${OG.esc(ctx.names[a > b ? 0 : 1])} — ${Math.max(a, b)} : ${Math.min(a, b)}`, a === b ? -1 : a > b ? 0 : 1);
          return;
        }
        if (!got) turn = 1 - turn;
        next(got);
      };
      const next = got => {
        draw();
        const who = ctx.mode === 'bot' ? (turn === 0 ? 'Ваш ход' : 'Ходит бот…') : `Ходит ${OG.esc(ctx.names[turn])}`;
        ctx.status(`${tally()}<br>${got ? 'Квадрат! ' : ''}${who}`);
        if (bot()) ctx.later(() => put(botMove(g, lines, ctx.opt.level)), got ? 450 : 550);
      };
      ctx.box.addEventListener('click', e => { const h = e.target.closest('[data-h]'); if (h && !busy && !bot()) put(+h.dataset.h); });
      next(0);
    },
  });
})(window.OG);
