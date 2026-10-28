/* Русские шашки: бить обязательно (можно выбрать, чем и как), простая бьёт и назад, бой продолжается до конца;
   дамка ходит и бьёт через любое число полей и обязана встать туда, откуда бой продолжается;
   шашка, дошедшая до последнего ряда во время боя, бьёт дальше уже как дамка. Битые снимаются после хода
   (турецкий удар: через одну шашку дважды не прыгают). Бот — negamax с альфа-бета, глубина 2 / 4 / 6. */
(function (OG) {
  'use strict';
  const DIRS = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
  const on = (r, c) => r >= 0 && r < 8 && c >= 0 && c < 8;
  // доска: массив 64, 1 — белая, 2 — белая дамка, -1 — чёрная, -2 — чёрная дамка; белые внизу и ходят первыми
  function initial() {
    const b = new Array(64).fill(0);
    for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) if ((r + c) % 2) { if (r < 3) b[r * 8 + c] = -1; else if (r > 4) b[r * 8 + c] = 1; }
    return b;
  }
  const lastRow = side => (side > 0 ? 0 : 7);

  function captures(b, from) {
    const side = Math.sign(b[from]), out = [];
    const piece = b[from];
    b[from] = 0;  // фигура «поднята»: её поле свободно
    (function dfs(pos, king, caps, path) {
      const r = Math.floor(pos / 8), c = pos % 8;
      let any = false;
      for (const [dr, dc] of DIRS) {
        let rr = r + dr, cc = c + dc;
        if (king) while (on(rr, cc) && b[rr * 8 + cc] === 0) { rr += dr; cc += dc; }
        if (!on(rr, cc)) continue;
        const x = rr * 8 + cc;
        if (Math.sign(b[x]) !== -side || caps.includes(x)) continue;
        const lands = [];
        let lr = rr + dr, lc = cc + dc;
        while (on(lr, lc) && b[lr * 8 + lc] === 0) { lands.push(lr * 8 + lc); if (!king) break; lr += dr; lc += dc; }
        if (!lands.length) continue;
        const nc = caps.concat(x);
        // дамка обязана встать на поле, откуда бой продолжается (если такое есть)
        const res = lands.map(l => { const k = king || Math.floor(l / 8) === lastRow(side); const more = cont(l, k, nc); return { l, k, more }; });
        const keep = res.some(x2 => x2.more) ? res.filter(x2 => x2.more) : res;
        for (const { l, k } of keep) { any = true; dfs(l, k, nc, path.concat(l)); }
      }
      if (!any && caps.length) out.push({ from, path, caps, king });
    })(from, Math.abs(piece) === 2, [], []);
    b[from] = piece;
    return out;

    function cont(pos, king, caps) {  // можно ли бить дальше с поля pos
      const r = Math.floor(pos / 8), c = pos % 8;
      for (const [dr, dc] of DIRS) {
        let rr = r + dr, cc = c + dc;
        if (king) while (on(rr, cc) && b[rr * 8 + cc] === 0) { rr += dr; cc += dc; }
        if (!on(rr, cc)) continue;
        const x = rr * 8 + cc;
        if (Math.sign(b[x]) !== -side || caps.includes(x)) continue;
        if (on(rr + dr, cc + dc) && b[(rr + dr) * 8 + cc + dc] === 0) return true;
      }
      return false;
    }
  }

  function moves(b, side) {
    const caps = [], quiet = [];
    for (let i = 0; i < 64; i++) {
      if (Math.sign(b[i]) !== side) continue;
      caps.push(...captures(b, i));
      if (caps.length) continue;
      const r = Math.floor(i / 8), c = i % 8, king = Math.abs(b[i]) === 2;
      for (const [dr, dc] of DIRS) {
        if (!king && dr !== -side) continue;  // простая ходит только вперёд
        let rr = r + dr, cc = c + dc;
        while (on(rr, cc) && b[rr * 8 + cc] === 0) {
          const to = rr * 8 + cc;
          quiet.push({ from: i, path: [to], caps: [], king: king || rr === lastRow(side) });
          if (!king) break;
          rr += dr; cc += dc;
        }
      }
    }
    return caps.length ? caps : quiet;
  }

  function apply(b, m) {
    const nb = b.slice(), side = Math.sign(b[m.from]);
    nb[m.from] = 0;
    m.caps.forEach(x => { nb[x] = 0; });
    nb[m.path[m.path.length - 1]] = m.king ? 2 * side : side;
    return nb;
  }

  function evaluate(b, side) {
    let s = 0;
    for (let i = 0; i < 64; i++) {
      const v = b[i];
      if (!v) continue;
      const r = Math.floor(i / 8), c = i % 8;
      let w = Math.abs(v) === 2 ? 300 : 100 + (v > 0 ? 7 - r : r) * 4;  // простые ценнее ближе к дамкам
      if (c >= 2 && c <= 5 && r >= 2 && r <= 5) w += 6;
      if (Math.abs(v) === 1 && r === (v > 0 ? 7 : 0)) w += 5;  // задний ряд не пускает в дамки
      s += Math.sign(v) === side ? w : -w;
    }
    return s;
  }
  function search(b, side, depth, alpha, beta) {
    const ms = moves(b, side);
    if (!ms.length) return -100000 - depth;  // нет ходов — проигрыш
    if (depth <= 0 && !ms[0].caps.length) return evaluate(b, side);
    if (depth <= -4) return evaluate(b, side);  // взятия досчитываем, но не бесконечно
    let best = -Infinity;
    for (const m of ms) {
      const v = -search(apply(b, m), -side, depth - 1, -beta, -alpha);
      if (v > best) best = v;
      if (best > alpha) alpha = best;
      if (alpha >= beta) break;
    }
    return best;
  }
  const DEPTH = { easy: 2, mid: 4, hard: 6 };
  function bestMove(b, side, level) {
    const ms = moves(b, side);
    if (ms.length === 1) return ms[0];
    if (level === 'easy' && Math.random() < .3) return OG.pick(ms);
    let best = -Infinity, pick = [];
    for (const m of ms) {
      const v = -search(apply(b, m), -side, (DEPTH[level] || 4) - 1, -Infinity, Infinity);
      if (v > best) { best = v; pick = [m]; } else if (v === best) pick.push(m);
    }
    return OG.pick(pick);
  }

  OG.add({
    id: 'checkers', title: 'Шашки', icon: 'circle', desc: 'Русские правила: бить обязательно, дамки', modes: ['bot', 'duo'],
    opts: [{ key: 'level', bot: true, def: 'mid', items: [['easy', 'Легко'], ['mid', 'Средне'], ['hard', 'Сложно']] }],
    ai: { initial, moves, apply, bestMove },
    start(ctx) {
      let b = initial(), side = 1, sel = -1, prefix = [], quiet = 0, lastMove = null, busy = false;
      const human = ctx.round % 2 ? -1 : 1;  // в игре с ботом цвета чередуются
      const flip = ctx.mode === 'bot' && human === -1;  // свои шашки — всегда внизу
      const sideName = s => (s > 0 ? 'белые' : 'чёрные');
      const nameOf = s => (ctx.mode === 'bot' ? (s === human ? 'Вы' : 'Бот') : ctx.names[s > 0 ? 0 : 1]);
      const idx = [...Array(64).keys()].map(i => (flip ? 63 - i : i));
      ctx.box.innerHTML = `<div class="og-chk">${idx.map(i => `<div class="${(Math.floor(i / 8) + i % 8) % 2 ? 'd' : 'l'}" data-i="${i}"></div>`).join('')}</div>`;
      const sq = {};
      ctx.box.querySelectorAll('[data-i]').forEach(el => { sq[el.dataset.i] = el; });
      const legal = () => moves(b, side);
      const draw = () => {
        const ms = busy || bot() ? [] : legal();
        const cand = sel >= 0 ? ms.filter(m => m.from === sel && prefix.every((p, k) => m.path[k] === p)) : [];
        const targets = new Set(cand.map(m => m.path[prefix.length]));
        const movable = new Set(ms.map(m => m.from));
        const pos = prefix.length ? prefix[prefix.length - 1] : sel;
        for (let i = 0; i < 64; i++) {
          const el = sq[i], v = b[i] && !(prefix.length && i === sel) ? b[i] : (prefix.length && i === pos ? b[sel] : 0);
          el.innerHTML = v ? `<span class="pc ${v > 0 ? 'w' : 'b'}">${Math.abs(v) === 2 ? OG.icon('crown') : ''}</span>` : '';
          el.classList.toggle('sel', i === pos && sel >= 0);
          el.classList.toggle('can', sel < 0 && movable.has(i));
          el.classList.toggle('to', targets.has(i));
          el.classList.toggle('last', !!lastMove && (lastMove.from === i || lastMove.path.includes(i)));
          el.classList.toggle('cap', prefix.length > 0 && cand.some(m => m.caps.slice(0, prefix.length).includes(i)));
        }
      };
      const bot = () => ctx.mode === 'bot' && side !== human;
      const finish = m => {
        const men = m.caps.length || Math.abs(b[m.from]) === 1;
        b = apply(b, m); lastMove = m; sel = -1; prefix = [];
        quiet = men ? 0 : quiet + 1;
        side = -side;
        next();
      };
      const next = () => {
        const ms = legal();
        if (!ms.length) {
          busy = true; draw();
          const w = -side;
          ctx.over(ctx.mode === 'bot' ? (w === human ? 'Вы победили!' : 'Бот победил') : `Победили ${sideName(w)} — ${OG.esc(nameOf(w))}`, ctx.mode === 'bot' ? (w === human ? 0 : 1) : (w > 0 ? 0 : 1));
          return;
        }
        if (quiet >= 30) { busy = true; draw(); ctx.over('Ничья: 15 ходов одними дамками без взятий', -1); return; }
        const must = ms[0].caps.length ? ' · <b>бить обязательно</b>' : '';
        if (bot()) {
          ctx.status(`Бот думает (${sideName(side)})…`); draw();
          ctx.later(() => finish(bestMove(b, side, ctx.opt.level)), 420);
        } else {
          ctx.status((ctx.mode === 'bot' ? `Ваш ход, у вас ${sideName(side)}` : `Ходят ${sideName(side)} — ${OG.esc(nameOf(side))}`) + must);
          draw();
        }
      };
      ctx.box.addEventListener('click', e => {
        const el = e.target.closest('[data-i]');
        if (!el || busy || bot()) return;
        const i = +el.dataset.i, ms = legal();
        if (sel >= 0) {
          const cand = ms.filter(m => m.from === sel && prefix.every((p, k) => m.path[k] === p) && m.path[prefix.length] === i);
          if (cand.length) {
            prefix.push(i);
            const done = cand.find(m => m.path.length === prefix.length);
            if (done) finish(done); else draw();  // бой продолжается: выберите следующее поле
            return;
          }
          if (prefix.length) return;  // посреди боя менять шашку нельзя
        }
        sel = ms.some(m => m.from === i) ? (sel === i ? -1 : i) : -1;
        draw();
      });
      next();
    },
  });
})(window.OG);
