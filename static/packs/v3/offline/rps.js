/* Камень, ножницы, бумага — до трёх побед. Вдвоём выбор делается по очереди втайне: между выборами
   экран «передайте телефон». Умный бот запоминает ваши привычки (что вы выбираете после своего прошлого хода)
   и бьёт самый вероятный выбор, но иногда ходит наугад — чтобы его самого нельзя было «прочитать». */
(function (OG) {
  'use strict';
  const OPTS = [['r', '✊', 'Камень'], ['p', '✋', 'Бумага'], ['s', '✌️', 'Ножницы']];
  const BEATS = { r: 's', s: 'p', p: 'r' }, COUNTER = { r: 'p', p: 's', s: 'r' };
  const EMO = Object.fromEntries(OPTS.map(o => [o[0], o[1]]));
  const TO_WIN = 3;
  function botPick(history, level) {  // history — прошлые выборы человека
    if (level === 'easy' || history.length < 3 || Math.random() < .15) return OG.pick('rps');
    const prev = history[history.length - 1], cnt = { r: 1, p: 1, s: 1 };
    for (let i = 1; i < history.length; i++) if (history[i - 1] === prev) cnt[history[i]] += 2;  // что идёт после такого же хода
    history.forEach(x => { cnt[x] += 1; });
    const guess = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a])[0];
    return COUNTER[guess];
  }
  const judge = (a, b) => (a === b ? -1 : BEATS[a] === b ? 0 : 1);

  OG.add({
    id: 'rps', title: 'Камень, ножницы, бумага', icon: 'wave', desc: 'До трёх побед, выбор держится в секрете', modes: ['bot', 'duo'],
    opts: [{ key: 'level', bot: true, def: 'hard', items: [['easy', 'Наугад'], ['hard', 'Читает привычки']] }],
    ai: { botPick, judge },
    start(ctx) {
      const score = [0, 0], rounds = [], mine = [];  // mine — выборы человека (для бота)
      const tally = () => `<div class="og-rps-score"><span>${OG.esc(ctx.names[0])}<b>${score[0]}</b></span><span class="muted">до ${TO_WIN}</span><span>${OG.esc(ctx.names[1])}<b>${score[1]}</b></span></div>`
        + (rounds.length ? `<div class="v3-rps-rounds">${rounds.map(([a, b, w], i) => `<span class="v3-rps-r"><i class="${w === 0 ? 'win' : ''}">${EMO[a]}</i><small>${i + 1}</small><i class="${w === 1 ? 'win' : ''}">${EMO[b]}</i></span>`).join('')}</div>` : '');
      const pickUI = (who, cb) => {
        ctx.box.innerHTML = tally() + `<div class="og-rps-pick">${OPTS.map(([k, e, n]) => `<button type="button" data-k="${k}"><span>${e}</span>${n}</button>`).join('')}</div>`;
        ctx.status(ctx.mode === 'bot' ? 'Ваш выбор?' : `${OG.esc(ctx.names[who])}, выбирайте — соперник не смотрит`);
        ctx.box.querySelectorAll('[data-k]').forEach(b => { b.onclick = () => cb(b.dataset.k); });
      };
      const reveal = (a, b) => {
        const w = judge(a, b);
        rounds.push([a, b, w]);
        if (w >= 0) score[w]++;
        ctx.box.innerHTML = tally() + `<div class="og-rps-vs"><div><span>${EMO[a]}</span>${OG.esc(ctx.names[0])}</div><b>:</b><div><span>${EMO[b]}</span>${OG.esc(ctx.names[1])}</div></div>`;
        const line = w < 0 ? 'Одинаково — ничья в раунде' : ctx.mode === 'bot' ? (w === 0 ? 'Раунд ваш!' : 'Раунд за ботом') : `Раунд за ${OG.esc(ctx.names[w])}`;
        if (score[0] >= TO_WIN || score[1] >= TO_WIN) {
          const p = score[0] > score[1] ? 0 : 1;
          ctx.over(`${line}. ${ctx.mode === 'bot' ? (p === 0 ? 'Вы победили' : 'Бот победил') : 'Победил ' + OG.esc(ctx.names[p])} ${score[p]} : ${score[1 - p]}`, p);
          return;
        }
        ctx.status(line);
        ctx.box.insertAdjacentHTML('beforeend', '<div class="og-row"><button type="button" class="btn" data-next>Следующий раунд</button></div>');
        ctx.box.querySelector('[data-next]').onclick = round;
      };
      const round = () => {
        if (ctx.mode === 'bot') { pickUI(0, k => { const bk = botPick(mine, ctx.opt.level); mine.push(k); reveal(k, bk); }); return; }
        // вдвоём: первым выбирает тот, у кого сейчас телефон (по очереди), второй — после передачи
        const first = rounds.length % 2, second = 1 - first, pick = [null, null];
        pickUI(first, k => { pick[first] = k; ctx.pass(ctx.names[second], () => pickUI(second, k2 => { pick[second] = k2; reveal(pick[0], pick[1]); }), 'Соперник уже выбрал'); });
      };
      round();
    },
  });
})(window.OG);
