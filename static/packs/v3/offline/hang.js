/* Виселица: угадайте слово по буквам, можно ошибиться 6 раз.
   С ботом — бот загадывает слово из встроенного словаря; вдвоём — один загадывает (слово скрыто), другой угадывает,
   в следующей партии наоборот. Буквы и слова приходят со страницы (OG.data), а не из кода. */
(function (OG) {
  'use strict';
  const LIVES = 6;
  const norm = w => String(w || '').trim().toLowerCase().replace(/\u0451/g, '\u0435');  // ё → е
  const valid = w => /^[\u0430-\u044f]{3,14}$/.test(w);
  const PARTS = ['<circle cx="70" cy="34" r="9"/>', '<line x1="70" y1="43" x2="70" y2="70"/>', '<line x1="70" y1="50" x2="58" y2="61"/>',
    '<line x1="70" y1="50" x2="82" y2="61"/>', '<line x1="70" y1="70" x2="60" y2="86"/>', '<line x1="70" y1="70" x2="80" y2="86"/>'];
  const gallows = miss => `<svg class="og-gal" viewBox="0 0 100 100"><path class="base" d="M10 94h50M22 94V8h48v17"/>${PARTS.slice(0, miss).join('')}</svg>`;

  OG.add({
    id: 'hang', title: 'Виселица', icon: 'type', desc: 'Угадайте слово по буквам — бот или друг загадывает', modes: ['bot', 'duo'],
    ai: { norm, valid },
    start(ctx) {
      const d = OG.data(), kb = d.kb || [], words = (d.words || []).filter(valid);
      const setter = ctx.mode === 'bot' ? 1 : ctx.round % 2, guesser = 1 - setter;
      let word = '', guessed = new Set(), done = false;
      const misses = () => [...guessed].filter(ch => !word.includes(ch)).length;
      const solved = () => [...word].every(ch => guessed.has(ch));
      const play = () => {
        ctx.box.innerHTML = `<div class="og-hang"><div class="og-hang-top">${gallows(misses())}<div class="og-hang-info"><div class="v3-hang-lives">${Array.from({ length: LIVES }, (_, i) => `<i class="${i < misses() ? 'gone' : ''}"></i>`).join('')}</div><span class="tiny muted">ошибок ${misses()} из ${LIVES}</span><span class="tiny muted">букв в слове: ${word.length}</span></div></div>`
          + `<div class="v3-hang-word og-hw">${[...word].map(ch => `<span class="${guessed.has(ch) ? 'open' : ''}">${guessed.has(ch) || done ? ch : ''}</span>`).join('')}</div>`
          + `<div class="v3-kb og-kb">${kb.map(row => `<div>${[...row].map(ch => `<button type="button" data-k="${ch}" class="${guessed.has(ch) ? (word.includes(ch) ? 'g' : 'n') : ''}"${guessed.has(ch) || done ? ' disabled' : ''}>${ch}</button>`).join('')}</div>`).join('')}</div></div>`;
      };
      const guess = ch => {
        if (done || guessed.has(ch) || !kb.join('').includes(ch)) return;
        guessed.add(ch);
        if (solved() || misses() >= LIVES) {
          done = true; play();
          const win = solved() ? guesser : setter;
          const text = solved() ? (ctx.mode === 'bot' ? 'Угадали!' : `${OG.esc(ctx.names[guesser])} угадал(а) слово`) : `Не угадали. Слово: «${word.toUpperCase()}»`;
          ctx.over(text, win);
          return;
        }
        play();
        ctx.status(word.includes(ch) ? 'Есть такая буква!' : 'Такой буквы нет');
      };
      const begin = () => {
        play();
        ctx.status(ctx.mode === 'bot' ? 'Бот загадал слово — угадывайте по буквам' : `${OG.esc(ctx.names[guesser])}, угадывайте слово`);
        ctx.box.addEventListener('click', e => { const b = e.target.closest('[data-k]'); if (b && !b.disabled) guess(b.dataset.k); });
        ctx.key(e => { const ch = norm(e.key); if (ch.length === 1) guess(ch); });
      };
      if (ctx.mode === 'bot') {
        if (!words.length) { ctx.status('Словарь не загрузился — откройте страницу ещё раз при подключении'); return; }
        word = OG.pick(words); begin(); return;
      }
      ctx.status(`${OG.esc(ctx.names[setter])} загадывает слово. ${OG.esc(ctx.names[guesser])}, не подглядывайте!`);
      ctx.box.innerHTML = `<form class="og-hang-set"><label class="small muted">Одно слово русскими буквами, от 3 до 14 букв</label>
        <input type="password" maxlength="14" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Например, черепаха" required>
        <label class="check"><input type="checkbox"><span>Показать слово</span></label><button class="btn block">Загадать</button></form>`;
      const f = ctx.box.querySelector('form'), inp = f.querySelector('input[type=password]');
      f.querySelector('input[type=checkbox]').onchange = e => { inp.type = e.target.checked ? 'text' : 'password'; };
      inp.focus();
      f.onsubmit = e => {
        e.preventDefault();
        const w = norm(inp.value);
        if (!valid(w)) { ctx.status('Нужно одно слово русскими буквами, от 3 до 14 букв'); return; }
        word = w; inp.value = '';
        ctx.pass(ctx.names[guesser], begin, 'Угадывать слово будете вы');
      };
    },
  });
})(window.OG);
