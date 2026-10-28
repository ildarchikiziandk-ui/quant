/* Морской бой 10×10: флот 4 + 3×2 + 2×3 + 1×4, корабли не касаются даже углами. Попал — стреляешь ещё.
   Вдвоём: каждый по очереди смотрит свою расстановку, между ходами — экран «передайте телефон».
   Бот: «охота» — после попадания добивает соседние клетки (а если попаданий два в линию — вдоль линии);
   умный бот ищет корабли по карте вероятностей (сколько оставшихся кораблей может накрыть клетку). */
(function (OG) {
  'use strict';
  const N = 10, FLEET = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1];
  const near = i => {  // клетка и её соседи (по сторонам и углам)
    const r = Math.floor(i / N), c = i % N, out = [];
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const rr = r + dr, cc = c + dc;
      if (rr >= 0 && rr < N && cc >= 0 && cc < N) out.push(rr * N + cc);
    }
    return out;
  };
  function place() {
    for (;;) {
      const busy = new Set(), ships = [];
      let ok = true;
      for (const size of FLEET) {
        let put = false;
        for (let t = 0; t < 300 && !put; t++) {
          const h = Math.random() < .5, r = OG.rnd(N - (h ? 0 : size - 1)), c = OG.rnd(N - (h ? size - 1 : 0));
          const cells = Array.from({ length: size }, (_, k) => (h ? r * N + c + k : (r + k) * N + c));
          if (cells.some(x => busy.has(x))) continue;
          ships.push(cells); cells.forEach(x => near(x).forEach(y => busy.add(y))); put = true;
        }
        if (!put) { ok = false; break; }
      }
      if (ok) return ships;
    }
  }
  // поле глазами стреляющего: 0 — неизвестно, 1 — мимо, 2 — ранен, 3 — потоплен, 4 — пусто рядом с потопленным
  function view(ships, shots) {
    const v = new Array(N * N).fill(0);
    shots.forEach(x => { v[x] = 1; });
    for (const s of ships) {
      const sunk = s.every(x => shots.has(x));
      if (sunk) s.forEach(x => near(x).forEach(y => { if (v[y] === 0 || v[y] === 1) v[y] = shots.has(y) ? 1 : 4; }));
      s.forEach(x => { if (shots.has(x)) v[x] = sunk ? 3 : 2; });
    }
    return v;
  }
  const left = (ships, shots) => ships.filter(s => !s.every(x => shots.has(x)));
  // карта вероятностей: сколькими способами оставшиеся корабли могут лечь на клетку
  function density(v, sizes) {
    const d = new Array(N * N).fill(0), hits = [];
    v.forEach((x, i) => { if (x === 2) hits.push(i); });
    for (const size of sizes) for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) for (const h of [true, false]) {
      if (h ? c + size > N : r + size > N) continue;
      const cells = Array.from({ length: size }, (_, k) => (h ? r * N + c + k : (r + k) * N + c));
      if (cells.some(x => v[x] !== 0 && v[x] !== 2)) continue;
      const cover = cells.filter(x => v[x] === 2).length;
      if (hits.length && !cover) continue;  // есть раненый — ищем только расстановки через него
      cells.forEach(x => { if (v[x] === 0) d[x] += 1 + cover * 20; });
    }
    return d;
  }
  function botShot(v, sizes, level) {
    const hits = [];
    v.forEach((x, i) => { if (x === 2) hits.push(i); });
    if (hits.length) {  // добиваем раненый корабль
      let cand = [];
      const rows = new Set(hits.map(i => Math.floor(i / N))), colsSet = new Set(hits.map(i => i % N));
      if (hits.length > 1 && (rows.size === 1 || colsSet.size === 1)) {
        const step = rows.size === 1 ? 1 : N, lo = Math.min(...hits), hi = Math.max(...hits);
        const ends = [lo - step, hi + step].filter(i => i >= 0 && i < N * N && (step === N || Math.floor(i / N) === Math.floor(lo / N)));
        cand = ends.filter(i => v[i] === 0);
      }
      if (!cand.length) {
        for (const i of hits) {
          const r = Math.floor(i / N), c = i % N;
          [[r - 1, c], [r + 1, c], [r, c - 1], [r, c + 1]].forEach(([rr, cc]) => { if (rr >= 0 && rr < N && cc >= 0 && cc < N && v[rr * N + cc] === 0) cand.push(rr * N + cc); });
        }
      }
      if (cand.length) {
        if (level !== 'hard') return OG.pick(cand);
        const d = density(v, sizes);
        const top = Math.max(...cand.map(i => d[i]));
        return OG.pick(cand.filter(i => d[i] === top));
      }
    }
    const free = [];
    v.forEach((x, i) => { if (x === 0) free.push(i); });
    if (level !== 'hard') return OG.pick(free);
    const d = density(v, sizes), top = Math.max(...free.map(i => d[i]));
    return OG.pick(free.filter(i => d[i] === top));
  }

  const CLS = ['', 'm', 'h', 's', 'x'];
  function boardHTML(ships, shots, reveal, click, lastShot, mini) {
    const v = view(ships, shots), own = new Set(reveal ? ships.flat() : []);
    return `<div class="v3-sea og-sea-b${mini ? ' mini' : ''}" style="--n:${N}">` + v.map((x, i) => {
      const cls = (CLS[x] || (own.has(i) ? 'o' : '')) + (i === lastShot ? ' last' : '');
      return click ? `<button type="button" class="${cls}" data-i="${i}"${x ? ' disabled' : ''} aria-label="${Math.floor(i / N) + 1}:${i % N + 1}"></button>` : `<i class="${cls}"></i>`;
    }).join('') + '</div>';
  }

  OG.add({
    id: 'sea', title: 'Морской бой', icon: 'target', desc: 'Поле 10×10, попал — стреляй ещё', modes: ['bot', 'duo'],
    opts: [{ key: 'level', bot: true, def: 'hard', items: [['easy', 'Полегче'], ['hard', 'Умный бот']] }],
    ai: { place, view, botShot, left, near, N, FLEET },
    start(ctx) {
      const P = [{ ships: place(), shots: new Set() }, { ships: place(), shots: new Set() }];  // shots — куда стрелял этот игрок
      const duo = ctx.mode === 'duo', box = ctx.box;
      let turn = ctx.round % 2, last = [-1, -1], busy = false;
      const fleetLeft = p => left(P[p].ships, P[1 - p].shots).length;
      const setup = (p, done) => {  // показываем расстановку, можно перемешать
        const draw = () => {
          box.innerHTML = `<div class="og-sea-cap">${duo ? `${OG.esc(ctx.names[p])}: ваш флот` : 'Ваш флот'}</div>${boardHTML(P[p].ships, new Set(), true, false)}`
            + `<div class="og-row"><button type="button" class="btn soft" data-sh>${OG.icon('shuffle')} Перемешать</button><button type="button" class="btn" data-go>${duo ? 'Готово' : 'В бой!'}</button></div>`;
          box.querySelector('[data-sh]').onclick = () => { P[p].ships = place(); draw(); };
          box.querySelector('[data-go]').onclick = done;
        };
        ctx.status('Корабли расставлены случайно. Не нравится — перемешайте.');
        draw();
      };
      let finished = false;
      const battle = () => {
        const me = turn, viewer = duo ? me : 0, other = 1 - viewer;  // вдвоём поля показываем глазами того, кто стреляет
        const canShoot = !busy && !finished && !(ctx.mode === 'bot' && me === 1);
        box.innerHTML = `<div class="og-sea-cap">Поле соперника · кораблей: ${fleetLeft(other)}</div>`
          + boardHTML(P[other].ships, P[viewer].shots, finished, canShoot, last[viewer])
          + `<div class="og-sea-cap">Ваш флот · кораблей: ${fleetLeft(viewer)}</div>`
          + boardHTML(P[viewer].ships, P[other].shots, true, false, last[other], true);
        if (finished) return;
        if (ctx.mode === 'bot' && me === 1) {
          ctx.status('Бот целится…');
          ctx.later(() => shoot(botShot(view(P[0].ships, P[1].shots), left(P[0].ships, P[1].shots).map(s => s.length), ctx.opt.level)), 650);
        } else ctx.status(duo ? `Стреляет ${OG.esc(ctx.names[me])}` : 'Ваш выстрел — нажмите на клетку поля соперника');
      };
      const shoot = i => {
        const me = turn, foe = 1 - me, botTurn = ctx.mode === 'bot' && me === 1;
        if (P[me].shots.has(i)) return;
        P[me].shots.add(i); last[me] = i;
        const ship = P[foe].ships.find(s => s.includes(i));
        if (!left(P[foe].ships, P[me].shots).length) {  // весь флот потоплен: открываем оба поля
          finished = true; battle();
          ctx.over(ctx.mode === 'bot' ? (me === 0 ? 'Вы победили — флот бота потоплен!' : 'Бот потопил весь ваш флот') : `Победил ${OG.esc(ctx.names[me])}!`, me);
          return;
        }
        if (ship) {  // попал — стреляет ещё
          battle();
          if (!botTurn) ctx.status(`<b>${ship.every(x => P[me].shots.has(x)) ? 'Корабль потоплен!' : 'Попадание!'}</b> Стреляйте ещё`);
          return;
        }
        if (!duo) { turn = foe; battle(); ctx.status(botTurn ? 'Бот промахнулся. Ваш выстрел' : 'Мимо. Стреляет бот…'); return; }
        busy = true; battle(); ctx.status('<b>Мимо.</b> Ход переходит сопернику');  // поле ещё глазами стрелявшего
        turn = foe;
        ctx.later(() => ctx.pass(ctx.names[foe], () => { busy = false; battle(); }, 'Ваша очередь стрелять'), 900);
      };
      box.addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (b && !b.disabled) shoot(+b.dataset.i); });
      if (duo) setup(0, () => ctx.pass(ctx.names[1], () => setup(1, () => ctx.pass(ctx.names[turn], battle, 'Вы стреляете первым'))));
      else setup(0, battle);
    },
  });
})(window.OG);
