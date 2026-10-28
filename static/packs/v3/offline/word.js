/* «Словечко» без сети: слово из 5 букв за 6 попыток. Слово дня берётся из встроенного словаря по дате
   (своё, не то же, что в онлайн-«Словечке»), в тренировке — случайное. Зелёная — буква на месте, жёлтая — есть в слове. */
(function (OG) {
  'use strict';
  function score(guess, answer) {  // как в онлайн-версии: повторы букв учитываются честно
    const res = ['n', 'n', 'n', 'n', 'n'], left = {};
    for (let i = 0; i < 5; i++) { if (guess[i] === answer[i]) res[i] = 'g'; else left[answer[i]] = (left[answer[i]] || 0) + 1; }
    for (let i = 0; i < 5; i++) if (res[i] !== 'g' && left[guess[i]]) { res[i] = 'y'; left[guess[i]]--; }
    return res.join('');
  }
  function hash(s) { let h = 2166136261; for (const ch of s) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619) >>> 0; } return h; }
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const norm = w => String(w || '').toLowerCase().replace(/\u0451/g, '\u0435');

  OG.add({
    id: 'word', title: 'Словечко', icon: 'book', desc: 'Слово из 5 букв за 6 попыток', modes: ['solo'],
    opts: [{ key: 'kind', def: 'day', items: [['day', 'Слово дня'], ['free', 'Тренировка']] }],
    ai: { score, hash },
    start(ctx) {
      const d = OG.data(), words = d.words5 || [], kb = d.kb || [], day = today(), daily = ctx.opt.kind === 'day';
      if (!words.length) { ctx.status('Словарь не загрузился — откройте страницу ещё раз при подключении'); return; }
      const answer = daily ? words[hash('nuvora-offline-' + day) % words.length] : OG.pick(words);
      const saved = daily ? OG.store.get('word:' + day, null) : null;
      const rows = saved && saved.rows ? saved.rows : [];
      let typed = '', over = false;
      const letters = kb.join('');
      ctx.box.innerHTML = '<div class="v3-word og-word"></div><div class="v3-kb og-wkb">' + kb.map((row, k) => `<div>${k === kb.length - 1 ? '<button type="button" data-k="Enter" class="wide">Ввод</button>' : ''}${[...row].map(ch => `<button type="button" data-k="${ch}">${ch}</button>`).join('')}${k === kb.length - 1 ? `<button type="button" data-k="Backspace" class="wide" aria-label="Стереть">${OG.icon('back')}</button>` : ''}</div>`).join('') + '</div>';
      const grid = ctx.box.querySelector('.og-word');
      const draw = () => {
        let html = '';
        for (let r = 0; r < 6; r++) {
          const row = rows[r], curRow = !row && r === rows.length && !over;
          html += `<div class="v3-wrow${curRow ? ' cur' : ''}">`;
          for (let i = 0; i < 5; i++) { const ch = row ? row[i] : curRow ? typed[i] || '' : ''; html += `<span class="${row ? score(row, answer)[i] : ch ? 'f' : ''}">${ch}</span>`; }
          html += '</div>';
        }
        grid.innerHTML = html;
        const best = {};
        rows.forEach(w => { const s = score(w, answer); [...w].forEach((ch, i) => { const o = best[ch]; best[ch] = s[i] === 'g' || o === 'g' ? 'g' : s[i] === 'y' || o === 'y' ? 'y' : 'n'; }); });
        ctx.box.querySelectorAll('.og-wkb [data-k]').forEach(b => { b.className = (b.classList.contains('wide') ? 'wide ' : '') + (best[b.dataset.k] || ''); });
        if (daily) OG.store.set('word:' + day, { rows });
      };
      const finish = () => {
        over = true; draw();
        const win = rows[rows.length - 1] === answer;
        ctx.over(win ? `Угадано с ${rows.length}-й попытки!${daily ? ' Новое слово — завтра' : ''}` : `Не получилось. Слово: «${answer.toUpperCase()}»`, win ? 0 : 1);
      };
      const press = k => {
        if (over) return;
        if (k === 'Backspace') typed = typed.slice(0, -1);
        else if (k === 'Enter') {
          if (typed.length < 5) { ctx.status('Нужно 5 букв'); const c = grid.querySelector('.cur'); if (c) { c.classList.add('shake'); ctx.later(() => c.classList.remove('shake'), 400); } return; }
          rows.push(typed); typed = '';
          if (rows[rows.length - 1] === answer || rows.length >= 6) { finish(); return; }
          ctx.status(`Попытка ${rows.length + 1} из 6`);
        } else {
          const ch = norm(k);
          if (ch.length === 1 && letters.includes(ch) && typed.length < 5) typed += ch;
        }
        draw();
      };
      ctx.box.querySelector('.og-wkb').addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (b) press(b.dataset.k); });
      ctx.key(e => press(e.key));
      if (rows.length && (rows[rows.length - 1] === answer || rows.length >= 6)) { finish(); return; }
      ctx.status(daily ? 'Слово дня — одно на сегодня. Введите первое слово' : 'Тренировка: случайное слово');
      draw();
    },
  });
})(window.OG);
