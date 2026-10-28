/* Судоку: генератор строит случайное решённое поле, затем убирает цифры (симметрично), пока у задачи
   остаётся ровно одно решение — это проверяет решатель с битовыми масками и выбором самой «узкой» клетки. */
(function (OG) {
  'use strict';
  const ROW = i => Math.floor(i / 9), COL = i => i % 9, BOX = i => Math.floor(ROW(i) / 3) * 3 + Math.floor(COL(i) / 3);
  const PEERS = Array.from({ length: 81 }, (_, i) => [...Array(81).keys()].filter(j => j !== i && (ROW(j) === ROW(i) || COL(j) === COL(i) || BOX(j) === BOX(i))));
  const bits = m => { let n = 0; while (m) { m &= m - 1; n++; } return n; };
  // число решений (не больше limit); g — массив 81, 0 — пусто. random — перебирать цифры в случайном порядке
  function solve(g, limit = 2, random = false) {
    const rows = new Array(9).fill(0), cols = new Array(9).fill(0), boxes = new Array(9).fill(0);
    for (let i = 0; i < 81; i++) if (g[i]) { const b = 1 << g[i]; if ((rows[ROW(i)] | cols[COL(i)] | boxes[BOX(i)]) & b) return 0; rows[ROW(i)] |= b; cols[COL(i)] |= b; boxes[BOX(i)] |= b; }
    let count = 0;
    (function rec() {
      let best = -1, bestFree = 0, bestN = 10;
      for (let i = 0; i < 81; i++) {
        if (g[i]) continue;
        const free = ~(rows[ROW(i)] | cols[COL(i)] | boxes[BOX(i)]) & 0x3fe, n = bits(free);
        if (n < bestN) { best = i; bestFree = free; bestN = n; if (n <= 1) break; }
      }
      if (best < 0) { count++; return count >= limit; }
      const ds = [];
      for (let d = 1; d <= 9; d++) if (bestFree & (1 << d)) ds.push(d);
      if (random) OG.shuffle(ds);
      for (const d of ds) {
        const b = 1 << d, r = ROW(best), c = COL(best), x = BOX(best);
        g[best] = d; rows[r] |= b; cols[c] |= b; boxes[x] |= b;
        if (rec()) return true;
        g[best] = 0; rows[r] &= ~b; cols[c] &= ~b; boxes[x] &= ~b;
      }
      return false;
    })();
    return count;
  }
  const CLUES = { easy: 40, mid: 32, hard: 25 };
  function generate(level) {
    const full = new Array(81).fill(0);
    solve(full, 1, true);  // решатель заполнит пустое поле случайными цифрами
    const puzzle = full.slice();
    let clues = 81;
    for (const i of OG.shuffle([...Array(41).keys()])) {  // пары клеток, симметричные относительно центра
      if (clues <= (CLUES[level] || 32)) break;
      const j = 80 - i, keep = [puzzle[i], puzzle[j]];
      puzzle[i] = puzzle[j] = 0;
      if (solve(puzzle.slice(), 2) !== 1) { puzzle[i] = keep[0]; puzzle[j] = keep[1]; } else clues -= i === j ? 1 : 2;
    }
    for (const i of OG.shuffle([...Array(81).keys()])) {  // для трудного уровня добираем по одной клетке
      if (clues <= (CLUES[level] || 32)) break;
      if (!puzzle[i]) continue;
      const keep = puzzle[i];
      puzzle[i] = 0;
      if (solve(puzzle.slice(), 2) !== 1) puzzle[i] = keep; else clues--;
    }
    return { puzzle, solution: full };
  }

  OG.add({
    id: 'sudoku', title: 'Судоку', icon: 'hash', desc: 'Цифры 1–9 без повторов в строке, столбце и квадрате', modes: ['solo'],
    opts: [{ key: 'level', def: 'easy', items: [['easy', 'Лёгкое'], ['mid', 'Среднее'], ['hard', 'Трудное']] }],
    ai: { solve, generate },
    start(ctx) {
      const { puzzle, solution } = generate(ctx.opt.level), g = puzzle.slice();
      let sel = -1, done = false, t0 = Date.now();
      ctx.box.innerHTML = `<div class="og-sud">${g.map((_, i) => `<button type="button" data-i="${i}" class="${puzzle[i] ? 'fix' : ''}${COL(i) % 3 === 2 && COL(i) < 8 ? ' br' : ''}${ROW(i) % 3 === 2 && ROW(i) < 8 ? ' bb' : ''}"></button>`).join('')}</div>`
        + `<div class="og-numpad">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(d => `<button type="button" data-d="${d}">${d}</button>`).join('')}<button type="button" data-d="0" aria-label="Стереть">${OG.icon('eraser')}</button></div>`;
      const cells = [...ctx.box.querySelectorAll('[data-i]')];
      const draw = () => {
        const bad = new Set();
        g.forEach((v, i) => { if (v && PEERS[i].some(j => g[j] === v)) bad.add(i); });
        const sv = sel >= 0 ? g[sel] : 0;
        cells.forEach((c, i) => {
          c.textContent = g[i] || '';
          c.classList.toggle('sel', i === sel);
          c.classList.toggle('peer', sel >= 0 && i !== sel && PEERS[sel].includes(i));
          c.classList.toggle('same', !!sv && g[i] === sv && i !== sel);
          c.classList.toggle('bad', bad.has(i));
        });
        const left = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        g.forEach(v => { left[v]++; });
        ctx.box.querySelectorAll('[data-d]').forEach(b => { const d = +b.dataset.d; b.classList.toggle('full', d > 0 && left[d] >= 9); });
      };
      const put = d => {
        if (done || sel < 0 || puzzle[sel]) return;
        g[sel] = d;
        draw();
        if (g.every((v, i) => v === solution[i])) {
          done = true; sel = -1; draw();
          const sec = Math.round((Date.now() - t0) / 1000);
          ctx.over(`Решено за ${Math.floor(sec / 60)} мин ${sec % 60} с!`, 0);
        }
      };
      ctx.box.addEventListener('click', e => {
        const c = e.target.closest('[data-i]'), d = e.target.closest('[data-d]');
        if (c && !done) { sel = +c.dataset.i; draw(); }
        if (d) put(+d.dataset.d);
      });
      ctx.key(e => {
        if (/^[1-9]$/.test(e.key)) put(+e.key);
        else if (e.key === 'Backspace' || e.key === 'Delete' || e.key === '0') put(0);
        else if (sel >= 0 && e.key.startsWith('Arrow')) { e.preventDefault(); const m = { ArrowUp: -9, ArrowDown: 9, ArrowLeft: -1, ArrowRight: 1 }[e.key]; sel = (sel + m + 81) % 81; draw(); }
      });
      ctx.status(`Подсказок: ${puzzle.filter(Boolean).length}. Выберите клетку и цифру`);
      draw();
    },
  });
})(window.OG);
