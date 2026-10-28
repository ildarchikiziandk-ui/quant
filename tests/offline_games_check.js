// Проверка логики «Игр без интернета» в node (запускается из tests/test_games_more.py): боты и правила без браузера.
'use strict';
const path = require('path'), assert = require('assert');
global.window = globalThis;
const DIR = path.join(__dirname, '..', 'static', 'packs', 'v3', 'offline');
const IDS = ['core', 'ttt', 'c4', 'sea', 'checkers', 'reversi', 'dots', 'nim', 'hang', 'rps', 'g2048', 'mines', 'snake', 'sudoku', 'fifteen', 'word'];
IDS.forEach(id => require(path.join(DIR, id + '.js')));
const ai = id => OG.games.find(g => g.id === id).ai;
assert.strictEqual(OG.games.length, IDS.length - 1);
const ok = (name, fn) => { const t = Date.now(); fn(); console.log('ok', name, Date.now() - t + 'ms'); };

ok('ttt 3x3: непобедимый бот не проигрывает ни при каких ходах человека', () => {
  const { winner, bestMove } = ai('ttt');
  let games = 0;
  const play = (b, turn, botSym) => {
    const w = winner(b, 3, 3);
    if (w) { assert.notStrictEqual(w.v, botSym === 'x' ? 'o' : 'x', 'бот проиграл: ' + b.join('')); games++; return; }
    if (b.every(Boolean)) { games++; return; }
    const next = turn === 'x' ? 'o' : 'x';
    if (turn === botSym) { const nb = b.slice(); nb[bestMove(nb, 3, 3, turn, 'hard')] = turn; play(nb, next, botSym); return; }
    b.forEach((v, i) => { if (!v) { const nb = b.slice(); nb[i] = turn; play(nb, next, botSym); } });
  };
  for (let k = 0; k < 2; k++) { play(Array(9).fill(''), 'x', 'o'); play(Array(9).fill(''), 'x', 'x'); }
  assert(games > 500);
});

ok('ttt 5x5: бот ставит четвёртый в ряд и закрывает угрозу', () => {
  const { bestMove } = ai('ttt');
  const b = Array(25).fill(''); b[0] = b[1] = b[2] = 'o'; b[10] = b[11] = 'x';
  assert.strictEqual(bestMove(b.slice(), 5, 4, 'o', 'hard'), 3);
  const c = Array(25).fill(''); c[5] = c[6] = c[7] = 'x'; c[0] = c[24] = 'o';
  assert([4, 8].includes(bestMove(c.slice(), 5, 4, 'o', 'hard')));
});

const randomGames = (n, run) => { let w = 0, l = 0; for (let i = 0; i < n; i++) { const r = run(i); if (r > 0) w++; else if (r < 0) l++; } return [w, l]; };

ok('c4: сильный бот обыгрывает случайного игрока и не проигрывает', () => {
  const { bestMove, wins, top } = ai('c4');
  const [w, l] = randomGames(8, i => {
    const b = new Int8Array(42), bot = i % 2 ? 1 : 2;
    for (let turn = 1; ; turn = 3 - turn) {
      const cols = [0, 1, 2, 3, 4, 5, 6].filter(c => top(b, c) >= 0);
      if (!cols.length) return 0;
      const c = turn === bot ? bestMove(b, turn, 'mid') : cols[Math.floor(Math.random() * cols.length)];
      const at = top(b, c); b[at] = turn;
      if (wins(b, at)) return turn === bot ? 1 : -1;
    }
  });
  assert.strictEqual(l, 0); assert(w >= 7, 'побед: ' + w);
  const b = new Int8Array(42); b[35] = b[36] = b[37] = 1;  // три в нижнем ряду — надо закрыть
  assert([34, 38].map(i => i % 7).includes(bestMove(b, 2, 'hard')));
  const t = Date.now(); bestMove(new Int8Array(42), 1, 'hard'); assert(Date.now() - t < 1500);
});

ok('морской бой: расстановка по правилам, бот добивает раненый корабль', () => {
  const { place, view, botShot, left, near, N, FLEET } = ai('sea');
  for (let k = 0; k < 200; k++) {
    const ships = place();
    assert.deepStrictEqual(ships.map(s => s.length).sort(), FLEET.slice().sort());
    ships.forEach((a, i) => ships.forEach((b, j) => { if (i !== j) assert(!a.some(x => near(x).some(y => b.includes(y))), 'корабли касаются'); }));
  }
  let total = 0;
  for (let k = 0; k < 20; k++) {
    const ships = place(), shots = new Set();
    let prevHit = -1;
    while (left(ships, shots).length) {
      const v = view(ships, shots), i = botShot(v, left(ships, shots).map(s => s.length), 'hard');
      assert(v[i] === 0, 'бот стреляет в известную клетку');
      if (prevHit >= 0) {  // после попадания по нетопленому — стреляет рядом с раненым
        const hits = []; v.forEach((x, j) => { if (x === 2) hits.push(j); });
        if (hits.length) assert(hits.some(h => Math.abs(h - i) === 1 || Math.abs(h - i) === N || hits.length > 1));
      }
      shots.add(i);
      prevHit = ships.some(s => s.includes(i)) ? i : -1;
      assert(shots.size <= N * N);
    }
    total += shots.size;
  }
  assert(total / 20 < 70, 'в среднем выстрелов: ' + total / 20);
});

ok('шашки: обязательное взятие, дамка бьёт издалека, превращение во время боя', () => {
  const { initial, moves, apply, bestMove } = ai('checkers');
  assert.strictEqual(moves(initial(), 1).length, 7);
  let b = new Array(64).fill(0); b[5 * 8 + 2] = 1; b[4 * 8 + 3] = -1; b[6 * 8 + 7] = 1;  // взятие обязательно
  const ms = moves(b, 1);
  assert.strictEqual(ms.length, 1); assert.deepStrictEqual(ms[0].caps, [35]);
  b = new Array(64).fill(0); b[7 * 8 + 0] = 2; b[5 * 8 + 2] = -1; b[2 * 8 + 5] = -1;  // дамка: два взятия по диагонали
  assert(moves(b, 1).every(m => m.caps.length === 2));
  b = new Array(64).fill(0); b[2 * 8 + 1] = 1; b[1 * 8 + 2] = -1; b[1 * 8 + 4] = -1;  // простая бьёт, становится дамкой и бьёт дальше
  const m = moves(b, 1);
  assert(m.some(x => x.caps.length === 2 && x.king), JSON.stringify(m));
  b = new Array(64).fill(0); b[3 * 8 + 2] = 1; b[4 * 8 + 3] = -1;  // простая бьёт назад
  assert.strictEqual(moves(b, 1)[0].caps[0], 35);
  const [w, l] = randomGames(4, i => {
    let bd = initial(), side = 1;
    const bot = i % 2 ? 1 : -1;
    for (let ply = 0; ply < 300; ply++) {
      const list = moves(bd, side);
      if (!list.length) return side === bot ? -1 : 1;
      bd = apply(bd, side === bot ? bestMove(bd, side, 'mid') : list[Math.floor(Math.random() * list.length)]);
      side = -side;
    }
    return 0;
  });
  assert.strictEqual(l, 0); assert(w >= 3, 'побед: ' + w);
  const t = Date.now(); bestMove(initial(), 1, 'hard'); assert(Date.now() - t < 2000);
});

ok('реверси: начальные ходы, бот сильнее случайного', () => {
  const { initial, moves, play, bestMove } = ai('reversi');
  assert.deepStrictEqual(moves(initial(), 1).sort((a, b) => a - b), [19, 26, 37, 44]);
  const [w] = randomGames(4, i => {
    let b = initial(), me = 1;
    const bot = i % 2 ? 1 : -1;
    for (;;) {
      let ms = moves(b, me);
      if (!ms.length) { me = -me; ms = moves(b, me); if (!ms.length) break; }
      b = play(b, me === bot ? bestMove(b, me, 'mid') : ms[Math.floor(Math.random() * ms.length)], me);
      me = -me;
    }
    const d = b.filter(v => v === bot).length - b.filter(v => v === -bot).length;
    return Math.sign(d);
  });
  assert(w >= 3, 'побед: ' + w);
});

ok('точки: бот забирает готовый квадрат и не даёт третью сторону', () => {
  const { game, botMove } = ai('dots');
  const g = game(3, 3), lines = new Array(g.total).fill(0);
  g.sides(1, 1).slice(0, 3).forEach(l => { lines[l] = 1; });
  assert.strictEqual(botMove(g, lines, 'hard'), g.sides(1, 1)[3]);
  const fresh = new Array(g.total).fill(0); fresh[g.sides(0, 0)[0]] = fresh[g.sides(0, 0)[1]] = 1;
  for (let k = 0; k < 20; k++) { const l = botMove(g, fresh, 'hard'); assert(!g.sides(0, 0).includes(l)); }
});

ok('ним: выигрышный ход оставляет нулевую ним-сумму', () => {
  const { best } = ai('nim');
  const [i, n] = best([3, 5, 7], false); const h = [3, 5, 7]; h[i] -= n;
  assert.strictEqual(h.reduce((a, x) => a ^ x, 0), 0);
  assert.strictEqual(best([1, 2, 3], false), null);
  assert.deepStrictEqual(best([0, 0, 5], true), [2, 4]);  // «последняя проигрывает»: оставить одну
  assert.strictEqual(best([1, 0, 0], true), null);
});

ok('камень-ножницы-бумага: умный бот ловит привычку', () => {
  const { botPick, judge } = ai('rps');
  assert.strictEqual(judge('r', 's'), 0); assert.strictEqual(judge('r', 'p'), 1); assert.strictEqual(judge('p', 'p'), -1);
  let botWins = 0; const hist = [];
  for (let k = 0; k < 60; k++) { const me = 'r'; if (judge(botPick(hist, 'hard'), me) === 0) botWins++; hist.push(me); }
  assert(botWins > 40, 'побед бота: ' + botWins);
});

ok('судоку: у задачи ровно одно решение', () => {
  const { solve, generate } = ai('sudoku');
  for (const lv of ['easy', 'mid', 'hard']) {
    const t = Date.now(), { puzzle, solution } = generate(lv);
    assert.strictEqual(solve(puzzle.slice(), 2), 1);
    assert(solution.every(Boolean) && puzzle.every((v, i) => !v || v === solution[i]));
    for (let k = 0; k < 9; k++) {
      assert.strictEqual(new Set(solution.slice(k * 9, k * 9 + 9)).size, 9);
      assert.strictEqual(new Set([0, 1, 2, 3, 4, 5, 6, 7, 8].map(r => solution[r * 9 + k])).size, 9);
    }
    assert(Date.now() - t < 3000, lv + ' слишком долго');
  }
});

ok('пятнашки, 2048, сапёр, змейка, словечко', () => {
  const f = ai('fifteen');
  for (let k = 0; k < 20; k++) {  // решаемость 4×4: чётность перестановки + ряд пустой клетки
    const b = f.shuffle(4), arr = b.filter(Boolean);
    let inv = 0; for (let i = 0; i < arr.length; i++) for (let j = i + 1; j < arr.length; j++) if (arr[i] > arr[j]) inv++;
    assert.strictEqual((inv + Math.floor(b.indexOf(0) / 4)) % 2, 1);
  }
  const t = ai('g2048');
  assert.deepStrictEqual(t.slide([2, 2, 2, 2]), [[4, 4, 0, 0], 8]);
  assert.deepStrictEqual(t.slide([0, 4, 4, 8]), [[8, 8, 0, 0], 8]);
  const mn = ai('mines'), mines = mn.lay(9, 9, 10, 40);
  assert.strictEqual(mines.size, 10); assert(![40, ...mn.around(9, 9, 40)].some(i => mines.has(i)));
  const sn = ai('snake'), s = { snake: [[0, 0]], dir: 'L', food: null };
  assert.strictEqual(sn.step(s, false), 'dead'); assert.strictEqual(sn.step(s, true), 'ok'); assert.deepStrictEqual(s.snake[0], [sn.N - 1, 0]);
  const w = ai('word');
  assert.strictEqual(w.score('ааббв', 'абагд'), 'gyynn');
});
console.log('all ok');
