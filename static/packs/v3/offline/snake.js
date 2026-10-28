/* Змейка 16×16: ешьте яблоки, не врезайтесь в себя. Стены — по выбору: сквозные или смертельные.
   Управление: смахивания по полю, кнопки-стрелки под ним или клавиатура. С каждым яблоком чуть быстрее. */
(function (OG) {
  'use strict';
  const N = 16, D = { U: [0, -1], D: [0, 1], L: [-1, 0], R: [1, 0] }, BACK = { U: 'D', D: 'U', L: 'R', R: 'L' };
  function step(s, wrap) {  // один шаг: { snake: [[x, y], …] голова первой, dir, food } → 'dead' | 'eat' | 'ok'
    const [dx, dy] = D[s.dir];
    let x = s.snake[0][0] + dx, y = s.snake[0][1] + dy;
    if (wrap) { x = (x + N) % N; y = (y + N) % N; } else if (x < 0 || y < 0 || x >= N || y >= N) return 'dead';
    const eat = s.food && x === s.food[0] && y === s.food[1];
    const body = eat ? s.snake : s.snake.slice(0, -1);
    if (body.some(([a, b]) => a === x && b === y)) return 'dead';
    s.snake = [[x, y], ...body];
    return eat ? 'eat' : 'ok';
  }
  function food(snake) {
    const free = [];
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) if (!snake.some(([a, b]) => a === x && b === y)) free.push([x, y]);
    return free.length ? OG.pick(free) : null;
  }

  OG.add({
    id: 'snake', title: 'Змейка', icon: 'activity', desc: 'Ешьте яблоки и растите, не врезаясь в себя', modes: ['solo'],
    opts: [{ key: 'walls', def: 'wrap', items: [['wrap', 'Сквозь стены'], ['walls', 'Со стенами']] }],
    ai: { step, food, N },
    start(ctx) {
      const wrap = ctx.opt.walls === 'wrap', key = 'best:snake:' + ctx.opt.walls;
      const s = { snake: [[7, 8], [6, 8], [5, 8]], dir: 'R', food: null };
      s.food = food(s.snake);
      let queue = [], score = 0, best = OG.store.get(key, 0), running = false, dead = false;
      ctx.box.innerHTML = `<div class="og-row og-scores"><div class="v3-gscore"><span>Яблоки</span><b data-s>0</b></div><div class="v3-gscore"><span>Рекорд</span><b data-b>${best}</b></div></div>`
        + '<canvas class="og-snake" width="320" height="320"></canvas>'
        + `<div class="og-pad">${['U', 'L', 'R', 'D'].map(d => `<button type="button" data-d="${d}" class="d${d}" aria-label="${{ U: 'Вверх', D: 'Вниз', L: 'Влево', R: 'Вправо' }[d]}">${OG.icon('back')}</button>`).join('')}</div>`;
      const cv = ctx.box.querySelector('canvas'), g = cv.getContext('2d'), Z = 320 / N;
      const css = n => getComputedStyle(document.body).getPropertyValue(n).trim();
      const draw = () => {
        g.fillStyle = css('--card-2') || '#fbf7f0'; g.fillRect(0, 0, 320, 320);
        g.fillStyle = css('--border') || '#e7ddcd';
        for (let y = 0; y < N; y++) for (let x = (y % 2); x < N; x += 2) g.fillRect(x * Z, y * Z, Z, Z);
        if (s.food) { g.fillStyle = '#e0475a'; g.beginPath(); g.arc(s.food[0] * Z + Z / 2, s.food[1] * Z + Z / 2, Z * .38, 0, 7); g.fill(); }
        const brand = css('--brand') || '#1f6fb8';
        s.snake.forEach(([x, y], i) => { g.fillStyle = i ? brand : css('--text') || '#1f1d1a'; g.globalAlpha = i ? 1 - Math.min(.5, i / (s.snake.length * 2)) : 1; g.fillRect(x * Z + 1, y * Z + 1, Z - 2, Z - 2); });
        g.globalAlpha = 1;
        ctx.box.querySelector('[data-s]').textContent = score;
      };
      const loop = () => {
        if (!running) return;
        if (!document.hidden) {
          while (queue.length) { const d = queue.shift(); if (d !== BACK[s.dir] && d !== s.dir) { s.dir = d; break; } }
          const r = step(s, wrap);
          if (r === 'dead') {
            running = false; dead = true; draw();
            const rec = score > best;
            if (rec) { best = score; OG.store.set(key, best); ctx.box.querySelector('[data-b]').textContent = best; }
            ctx.over(`Конец игры: ${score} ${rec ? '— новый рекорд!' : ''}`, rec ? 0 : null);
            return;
          }
          if (r === 'eat') { score++; s.food = food(s.snake); }
          draw();
        }
        ctx.later(loop, Math.max(70, 170 - score * 4));
      };
      const turn = d => {
        if (dead) return;
        queue.push(d); if (queue.length > 3) queue.shift();
        if (!running) { running = true; ctx.status('Вперёд!'); loop(); }
      };
      ctx.swipe(cv, turn);
      ctx.box.querySelector('.og-pad').addEventListener('click', e => { const b = e.target.closest('[data-d]'); if (b) turn(b.dataset.d); });
      ctx.key(e => { const d = { ArrowUp: 'U', ArrowDown: 'D', ArrowLeft: 'L', ArrowRight: 'R', w: 'U', s: 'D', a: 'L', d: 'R' }[e.key]; if (d) { e.preventDefault(); turn(d); } });
      ctx.status('Смахните или нажмите стрелку, чтобы начать');
      draw();
    },
  });
})(window.OG);
