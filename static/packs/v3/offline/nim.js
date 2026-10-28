/* Ним (спички): три кучки — 3, 5 и 7. За ход берут сколько угодно спичек, но из одной кучки.
   Правило выбирается: кто взял последнюю — выиграл или проиграл. Сильный бот играет по «ним-сумме» (XOR):
   оставляет сопернику позицию с нулевой суммой, а в варианте «последняя проигрывает» под конец оставляет нечётное число кучек по одной. */
(function (OG) {
  'use strict';
  function best(heaps, misere) {  // [кучка, сколько взять] или null, если выигрышного хода нет
    const big = heaps.filter(h => h > 1).length;
    if (misere && big <= 1) {
      // все кучки (кроме, может быть, одной) по одной спичке: оставляем нечётное число единичных кучек
      const ones = heaps.filter(h => h === 1).length;
      if (big === 1) { const i = heaps.findIndex(h => h > 1); return [i, ones % 2 ? heaps[i] : heaps[i] - 1]; }
      return ones % 2 ? null : [heaps.findIndex(h => h === 1), 1];
    }
    const x = heaps.reduce((a, h) => a ^ h, 0);
    if (!x) return null;
    const i = heaps.findIndex(h => (h ^ x) < h);
    return [i, heaps[i] - (heaps[i] ^ x)];
  }
  function botMove(heaps, misere, level) {
    const win = level === 'easy' && Math.random() < .5 ? null : best(heaps, misere);
    if (win) return win;
    const live = heaps.map((h, i) => [h, i]).filter(([h]) => h > 0);
    const [h, i] = OG.pick(live);
    return [i, 1 + OG.rnd(Math.min(h, 3))];  // проигрышная позиция — берём немного и ждём ошибки
  }

  OG.add({
    id: 'nim', title: 'Спички (ним)', icon: 'flame', desc: 'Три кучки, берите из одной сколько хотите', modes: ['bot', 'duo'],
    opts: [{ key: 'rule', def: 'lose', items: [['lose', 'Последняя проигрывает'], ['win', 'Последняя выигрывает']] },
           { key: 'level', bot: true, def: 'hard', items: [['easy', 'Полегче'], ['hard', 'Без ошибок']] }],
    ai: { best, botMove },
    start(ctx) {
      const heaps = [3, 5, 7], misere = ctx.opt.rule === 'lose';
      let turn = ctx.round % 2, sel = null, busy = false;  // sel — [кучка, с какой спички берём]
      const bot = () => ctx.mode === 'bot' && turn === 1;
      const draw = () => {
        ctx.box.innerHTML = '<div class="og-nim">' + heaps.map((h, i) => `<div class="og-heap" data-h="${i}">`
          + Array.from({ length: h }, (_, k) => `<button type="button" class="og-match${sel && sel[0] === i && k >= sel[1] ? ' on' : ''}" data-h="${i}" data-k="${k}" aria-label="Кучка ${i + 1}, спичка ${k + 1}"${busy || bot() ? ' disabled' : ''}></button>`).join('')
          + `<span class="og-heap-n">${h}</span></div>`).join('') + '</div>'
          + `<div class="og-row"><button type="button" class="btn" data-take${sel ? '' : ' disabled'}>${sel ? `Взять ${heaps[sel[0]] - sel[1]}` : 'Выберите спички'}</button></div>`;
        ctx.box.querySelector('[data-take]').onclick = () => { if (sel) take(sel[0], heaps[sel[0]] - sel[1]); };
      };
      const take = (i, k) => {
        heaps[i] -= k; sel = null;
        const who = turn;
        if (heaps.every(h => !h)) {
          busy = true; draw();
          const w = misere ? 1 - who : who;
          ctx.over(ctx.mode === 'bot' ? (w === 0 ? 'Вы победили!' : 'Бот победил') : `Победил ${OG.esc(ctx.names[w])}`, w);
          return;
        }
        turn = 1 - turn;
        next(who, k);
      };
      const next = (who, k) => {
        draw();
        const was = who === undefined ? '' : `${ctx.mode === 'bot' ? (who === 1 ? 'Бот взял' : 'Вы взяли') : OG.esc(ctx.names[who]) + ' берёт'}: ${k}. `;
        ctx.status(was + (bot() ? 'Бот думает…' : ctx.mode === 'bot' ? 'Ваш ход: нажмите на спичку — возьмёте её и все правее' : `Ходит ${OG.esc(ctx.names[turn])}`));
        if (bot()) ctx.later(() => { const [i, n] = botMove(heaps, misere, ctx.opt.level); take(i, n); }, 700);
      };
      ctx.box.addEventListener('click', e => {
        const m = e.target.closest('.og-match');
        if (!m || m.disabled) return;
        const i = +m.dataset.h, k = +m.dataset.k;
        sel = sel && sel[0] === i && sel[1] === k ? null : [i, k];
        draw();
      });
      next();
      ctx.status((misere ? 'Последняя спичка проигрывает. ' : 'Последняя спичка выигрывает. ') + (bot() ? 'Бот думает…' : ctx.mode === 'bot' ? 'Ваш ход: нажмите на спичку — возьмёте её и все правее' : `Ходит ${OG.esc(ctx.names[turn])}`));
    },
  });
})(window.OG);
