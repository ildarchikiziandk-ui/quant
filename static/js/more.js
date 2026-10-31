/* Nuvora 2.0 — новые функции интерфейса. Каждая функция отдельная и отключается в настройках (services/prefs.py).
   Если какая-то часть падает, остальные продолжают работать. */
(function () {
  'use strict';
  const APP = window.APP || {};
  const P = APP.prefs || {};
  // для гостей настроек нет — берём значения по умолчанию
  const DEFAULT_ON = new Set(['feed_new_pill', 'feed_keep_scroll', 'scroll_top_btn', 'pull_refresh', 'reading_progress', 'desktop_notify',
    'app_badge', 'emoji_autoreplace', 'layout_fix', 'dbl_tap_react', 'chat_commands', 'char_counter', 'greeting', 'haptics',
    'command_palette', 'tap_top']);
  const on = (k) => (P[k] === undefined ? DEFAULT_ON.has(k) : !!P[k]);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* приватный режим */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* приватный режим */ } },
  };
  const toast = (t, err) => window.App && App.toast ? App.toast(t, err) : null;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const IC = (n) => window.ICON ? ICON(n, 'i') : '';
  const path = location.pathname;
  // дата по часам устройства (а не UTC): иначе в Москве «сегодня» начиналось бы в 3 часа ночи
  const localDate = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const safe = (name, fn) => { try { fn(); } catch (e) { console.warn('[nuvora] ' + name, e); } };
  window.NV = { on, ls, esc };

  // ======================================================================== ОБЩЕЕ
  // 1. Кнопка «Наверх»
  safe('scrolltop', () => {
    if (!on('scroll_top_btn') || $('#box')) return;
    const b = document.createElement('button'); b.type = 'button'; b.className = 'to-top hidden'; b.title = 'Наверх'; b.innerHTML = IC('back');
    b.onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' }); document.body.appendChild(b);
    addEventListener('scroll', () => b.classList.toggle('hidden', scrollY < 1200), { passive: true });
  });

  // 2. Потянуть, чтобы обновить (телефон)
  safe('pull', () => {
    if (!on('pull_refresh') || !('ontouchstart' in window) || $('#box') || path.startsWith('/stories') || path.startsWith('/reels')) return;
    const ind = document.createElement('div'); ind.className = 'ptr'; ind.innerHTML = IC('refresh'); document.body.appendChild(ind);
    let y0 = null, dy = 0;
    addEventListener('touchstart', e => { y0 = scrollY <= 0 && !e.target.closest('.modal-bg.open,.mmenu:not([hidden]),input,textarea') ? e.touches[0].clientY : null; dy = 0; }, { passive: true });
    addEventListener('touchmove', e => { if (y0 === null) return; dy = e.touches[0].clientY - y0; if (dy > 0) { ind.style.transform = `translate(-50%, ${Math.min(dy, 120) - 50}px) rotate(${dy * 3}deg)`; ind.style.opacity = Math.min(1, dy / 90); } }, { passive: true });
    addEventListener('touchend', () => { if (y0 !== null && dy > 95) { ind.classList.add('spin'); vib(10); location.reload(); } else { ind.style.transform = ''; ind.style.opacity = 0; } y0 = null; });
  });

  // 3. Плашка «Нет подключения»
  safe('offline', () => {
    const bar = document.createElement('div'); bar.className = 'net-bar hidden'; document.body.appendChild(bar);
    const show = (online) => { bar.textContent = online ? 'Снова в сети' : 'Нет подключения к интернету'; bar.classList.toggle('ok', online); bar.classList.remove('hidden'); if (online) setTimeout(() => bar.classList.add('hidden'), 2500); };
    addEventListener('offline', () => show(false)); addEventListener('online', () => show(true));
    if (navigator.onLine === false) show(false);
    // страницу отдали из сохранённых (сеть пропала или тормозит): говорим об этом и даём обновить
    if (document.documentElement.dataset.savedCopy) {
      bar.innerHTML = 'Сохранённая копия · <u>обновить</u>';
      bar.classList.remove('hidden', 'ok'); bar.classList.add('saved'); bar.style.cursor = 'pointer'; bar.onclick = () => location.reload();
    }
    // в списке чатов заранее сохраняем последние переписки (только текст), чтобы читать их без сети
    if (location.pathname === '/messages' && navigator.onLine !== false && navigator.serviceWorker && navigator.serviceWorker.controller && !document.documentElement.dataset.savedCopy) {
      const last = +ls.get('nv_chats_cached') || 0;
      if (Date.now() - last > 10 * 60 * 1000) {
        const urls = [...new Set([...document.querySelectorAll('a[href^="/messages/"]')].map(a => a.getAttribute('href')).filter(h => /^\/messages\/[\w.-]+$/.test(h) && !/^\/messages\/(starred|search)$/.test(h)))].slice(0, 10);
        if (urls.length) { navigator.serviceWorker.controller.postMessage({ type: 'cache-pages', urls }); ls.set('nv_chats_cached', String(Date.now())); }
      }
    }
  });

  // 4. Виброотклик: можно выключить
  function vib(ms) { if (on('haptics')) try { navigator.vibrate && navigator.vibrate(ms); } catch (e) { /* нет вибро */ } }
  safe('haptics', () => {
    if (!on('haptics') && navigator.vibrate) navigator.vibrate = () => false;
    window.NV.vib = vib;
  });

  // 5. Время в приложении сегодня + 6. напоминание отдохнуть
  safe('screentime', () => {
    if (!APP.user) return;
    const key = 'nv_time_' + localDate();
    let session = 0; const limit = (+P.break_reminder || 0) * 60;
    setInterval(() => {
      if (document.hidden) return;
      ls.set(key, String((+ls.get(key, 0)) + 30)); session += 30;
      if (limit && session >= limit) { session = 0; window.App && App.modal && App.modal('Время сделать перерыв', `<p class="muted">Вы в ${esc(document.title.split('—').pop().trim() || 'Nuvora')} уже ${Math.round(limit / 60)} минут подряд. Разомнитесь, попейте воды и дайте глазам отдохнуть.</p><button class="btn block mt" data-close>Хорошо</button>`); }
    }, 30000);
    document.addEventListener('visibilitychange', () => { if (document.hidden) session = Math.max(0, session - 60); });
    const fmt = (s) => s < 60 ? 'меньше минуты' : s < 3600 ? Math.round(s / 60) + ' мин' : (s / 3600).toFixed(1).replace('.', ',') + ' ч';
    const out = $('#time-today');
    if (out) out.textContent = fmt(+ls.get(key, 0));
    const wk = $('#time-week');
    if (wk) {  // последние 7 дней столбиками
      const days = []; for (let i = 6; i >= 0; i--) { const d = new Date(Date.now() - i * 86400000); const k2 = 'nv_time_' + d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); days.push([d, +ls.get(k2, 0)]); }
      const max = Math.max(60, ...days.map(x => x[1])), total = days.reduce((a, x) => a + x[1], 0);
      wk.innerHTML = '<div class="tw-bars">' + days.map(([d, s]) => `<div title="${fmt(s)}"><i style="height:${Math.round(s / max * 100)}%"></i><span>${['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'][d.getDay()]}</span></div>`).join('') + '</div><div class="small muted">За неделю: <b>' + fmt(total) + '</b></div>';
    }
  });

  // 7. Размытие при сворачивании
  safe('privacyblur', () => {
    if (!P.privacy_blur) return;
    document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('nv-blurred', document.hidden));
    addEventListener('blur', () => document.documentElement.classList.add('nv-blurred'));
    addEventListener('focus', () => document.documentElement.classList.remove('nv-blurred'));
  });

  // 8. Счётчик на значке приложения, 9. уведомления браузера, 10. звук уведомления
  safe('counters', () => {
    if (!APP.user) return;
    let last = null;
    const handle = (r) => {
      const total = (r.notifications || 0) + (r.messages || 0);
      if (on('app_badge') && navigator.setAppBadge) { try { total ? navigator.setAppBadge(total) : navigator.clearAppBadge(); } catch (e) { /* не поддерживается */ } }
      if (last && document.hidden && on('desktop_notify') && window.Notification && Notification.permission === 'granted' && !/NuvoraApp/.test(navigator.userAgent)) {
        if (r.messages > last.messages) new Notification('Новое сообщение', { body: 'Непрочитанных: ' + r.messages, icon: '/static/icon-192.png', tag: 'nv-msg' }).onclick = () => { focus(); location.href = '/messages'; };
        else if (r.notifications > last.notifications) new Notification('Новое уведомление', { body: 'Непрочитанных: ' + r.notifications, icon: '/static/icon-192.png', tag: 'nv-notif' }).onclick = () => { focus(); location.href = '/notifications'; };
      }
      last = r;
    };
    addEventListener('nv:counters', e => handle(e.detail || {}));
    // пока вкладка свёрнута, основной опрос стоит — проверяем реже и без статуса «в сети»
    setInterval(async () => {
      if (!document.hidden || !on('desktop_notify') || !window.Notification || Notification.permission !== 'granted' || APP.push) return;
      try { const r = await (await fetch('/api/counters?bg=1', { headers: { 'X-Requested-With': 'fetch' } })).json(); if (r.ok) handle(r); } catch (e) { /* нет сети */ }
    }, 45000);
  });

  // 11. Предупреждение о внешних ссылках
  safe('extwarn', () => {
    if (!P.external_warn) return;
    document.addEventListener('click', e => {
      const a = e.target.closest('a[href^="http"]'); if (!a || a.host === location.host) return;
      if (!confirm('Вы уходите с Nuvora на сайт ' + a.host + '. Продолжить?')) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, true);
  });

  // 12. Копирование кода по нажатию
  document.addEventListener('click', e => {
    const c = e.target.closest('code.rt-code'); if (!c || !navigator.clipboard) return;
    navigator.clipboard.writeText(c.textContent).then(() => toast('Код скопирован'));
  });

  // 13. Счётчик символов в длинных полях
  safe('counter', () => {
    if (!on('char_counter')) return;
    const attach = (el) => {
      const max = +el.getAttribute('maxlength'); if (!max || max < 200 || el.dataset.cnt || el.closest('#composer')) return;
      el.dataset.cnt = 1; const c = document.createElement('div'); c.className = 'char-cnt hidden'; el.after(c);
      const upd = () => { const n = el.value.length; c.classList.toggle('hidden', n < max * 0.7); c.classList.toggle('warn', n > max * 0.95); c.textContent = (max - n) + ' символов осталось'; };
      el.addEventListener('input', upd);
    };
    $$('textarea[maxlength], input[maxlength]').forEach(attach);
    if (!window.MutationObserver) return;
    new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) (n.matches && n.matches('textarea[maxlength],input[maxlength]') ? [n] : $$('textarea[maxlength], input[maxlength]', n)).forEach(attach); }))).observe(document.body, { childList: true, subtree: true });
  });

  // 14. Автозамена смайликов
  const SMILES = { ':)': '🙂', ':-)': '🙂', ':D': '😄', ':(': '🙁', ';)': '😉', ':P': '😛', ':p': '😛', '<3': '❤️', ':*': '😘', 'xD': '😆', 'XD': '😆', ':o': '😮', ':O': '😮', '8)': '😎', ":'(": '😢', '+1': '👍' };
  safe('smiles', () => {
    if (!on('emoji_autoreplace')) return;
    document.addEventListener('input', e => {
      const el = e.target; if (!el.matches || !el.matches('#inp, textarea[name=content], input[name=content], .gc-input, textarea[name=text]') || e.inputType !== 'insertText' || e.data !== ' ') return;
      const pos = el.selectionStart, before = el.value.slice(0, pos - 1), m = before.match(/(^|\s)(\S{2,3})$/);
      if (!m || !SMILES[m[2]]) return;
      const start = before.length - m[2].length, rep = SMILES[m[2]];
      el.value = el.value.slice(0, start) + rep + el.value.slice(pos - 1); el.selectionStart = el.selectionEnd = start + rep.length + 1;
    });
  });

  // 15. «Исправить раскладку»: ghbdtn → привет
  const EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~";
  const RU = 'йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ';
  const toRu = (s) => s.replace(/[\s\S]/g, ch => { const i = EN.indexOf(ch); return i >= 0 ? RU[i] : ch; });
  function wrongLayout(s) {
    const t = s.trim(); if (t.length < 4 || /[а-яё]/i.test(t) || !/^[a-z\[\];',.`{}:"<>~\s\d!?-]+$/i.test(t) || /https?:|www\.|@/.test(t)) return false;
    const letters = t.replace(/[^a-z]/gi, ''); if (letters.length < 3) return false;
    const vowels = (letters.match(/[aeiouy]/gi) || []).length / letters.length;
    return vowels < 0.2 || /[a-z][\[\];',.][a-z]/i.test(t);
  }
  safe('layout', () => {
    if (!on('layout_fix')) return;
    const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'layout-chip hidden'; document.body.appendChild(chip);
    let target = null;
    document.addEventListener('input', e => {
      const el = e.target; if (!el.matches || !el.matches('#inp, textarea, input[type=search], input[name=q], input[name=content]')) return;
      if (wrongLayout(el.value)) { target = el; chip.innerHTML = IC('keyboard') + ' Исправить на «' + esc(toRu(el.value.trim()).slice(0, 24)) + '»'; const r = el.getBoundingClientRect(); chip.style.left = Math.max(8, r.left) + 'px'; chip.style.top = Math.max(8, r.top - 40) + 'px'; chip.classList.remove('hidden'); }
      else chip.classList.add('hidden');
    });
    chip.addEventListener('pointerdown', e => e.preventDefault());
    chip.onclick = () => { if (!target) return; target.value = toRu(target.value); target.dispatchEvent(new Event('input', { bubbles: true })); target.focus(); chip.classList.add('hidden'); };
    document.addEventListener('focusout', () => setTimeout(() => { if (!document.activeElement || document.activeElement !== target) chip.classList.add('hidden'); }, 150));
    window.NV.toRu = toRu; window.NV.wrongLayout = wrongLayout;
  });

  // 16. Быстрый переход Ctrl+K
  safe('palette', () => {
    if (!APP.user || !on('command_palette')) return;
    const PAGES = [['Лента', '/', 'home'], ['Сообщения', '/messages', 'chat'], ['Уведомления', '/notifications', 'bell'], ['Мой профиль', '/profile/' + APP.user, 'user'],
      ['Новый пост', '/create', 'plus'], ['Обзор', '/explore', 'compass'], ['Поиск', '/search', 'search'], ['Закладки', '/bookmarks', 'bookmark'], ['Избранные сообщения', '/messages/starred', 'star'],
      ['Группы', '/groups', 'users'], ['Дни рождения', '/birthdays', 'cake'], ['События', '/events', 'calendar'], ['Задания', '/tasks', 'target'], ['Заметки', '/notes', 'note'],
      ['Черновики', '/drafts', 'draft'], ['Статистика', '/stats', 'chart'], ['Гости профиля', '/guests', 'eye'], ['Подарки', '/gifts/' + APP.user, 'gift'], ['Достижения', '/achievements', 'medal'],
      ['Колесо фортуны', '/wheel', 'wheel'], ['Магазин', '/shop', 'bag'], ['Что нового', '/whats-new', 'sparkle'], ['Настройки', '/settings', 'settings'], ['Оформление', '/settings?section=appearance', 'palette'],
      ['Приватность', '/settings?section=privacy', 'lock'], ['Безопасность и код-пароль', '/settings?section=security', 'shield'], ['Уведомления: настройки', '/settings?section=notifications', 'bell'],
      ['Настройки чатов', '/settings?section=messages', 'chat'], ['Доступность', '/settings?section=accessibility', 'accessibility'], ['Мои данные', '/settings?section=data', 'package'], ['Поддержка', '/support', 'lifebuoy'],
      ['Действие: сменить тему', 'javascript:toggleTheme()', 'contrast'], ['Действие: наверх страницы', 'javascript:scrollTo(0,0)', 'back'], ['Действие: новая история', '/stories/create', 'camera']];
    let md = null, sel = 0, items = [];
    function render(q) {
      const list = $('.pal-list', md); q = q.trim().toLowerCase();
      items = PAGES.filter(p => !q || p[0].toLowerCase().includes(q)).slice(0, 8).map(p => ({ label: p[0], href: p[1], ic: p[2] }));
      draw();
      if (q.length >= 2) fetch('/api/users/suggest?q=' + encodeURIComponent(q.replace(/^@/, ''))).then(r => r.json()).then(r => {
        if ($('.pal-in', md).value.trim().toLowerCase() !== q) return;
        items = items.concat((r.users || []).slice(0, 5).map(u => ({ label: u.name + ' · @' + u.username, href: '/profile/' + u.username, ic: 'user' }))); draw();
      }).catch(() => {});
      function draw() { sel = Math.min(sel, Math.max(0, items.length - 1)); list.innerHTML = items.map((it, i) => `<a href="${esc(it.href)}" class="pal-item${i === sel ? ' sel' : ''}">${IC(it.ic)}<span>${esc(it.label)}</span></a>`).join('') || '<div class="muted small" style="padding:10px">Ничего не найдено</div>'; }
    }
    function go(href) { if (href.startsWith('javascript:')) { md.classList.remove('open'); if (href.includes('toggleTheme')) window.toggleTheme && toggleTheme(); else scrollTo(0, 0); } else location.href = href; }
    function open() {
      if (!md) { md = document.createElement('div'); md.className = 'modal-bg pal-bg'; md.innerHTML = '<div class="modal pal"><input class="pal-in" placeholder="Куда перейти? Раздел или @человек" autocomplete="off"><div class="pal-list"></div><div class="tiny faint" style="padding:8px 4px 0">↑↓ — выбрать · Enter — открыть · Esc — закрыть</div></div>'; document.body.appendChild(md);
        md.addEventListener('click', e => { if (e.target === md) md.classList.remove('open'); const a = e.target.closest('.pal-item'); if (a && a.getAttribute('href').startsWith('javascript:')) { e.preventDefault(); go(a.getAttribute('href')); } });
        const inp = $('.pal-in', md);
        inp.addEventListener('input', () => { sel = 0; render(inp.value); });
        inp.addEventListener('keydown', e => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % Math.max(1, items.length); $$('.pal-item', md).forEach((a, i) => a.classList.toggle('sel', i === sel)); }
          else if (e.key === 'Enter' && items[sel]) go(items[sel].href);
          else if (e.key === 'Escape') md.classList.remove('open');
        });
      }
      md.classList.add('open'); const inp = $('.pal-in', md); inp.value = ''; render(''); setTimeout(() => inp.focus(), 30);
    }
    document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'л')) { e.preventDefault(); open(); } });
    window.NV.palette = open;
  });

  // 17. Повторное нажатие на вкладку внизу — наверх
  safe('taptop', () => {
    if (!on('tap_top')) return;
    document.addEventListener('click', e => {
      const a = e.target.closest('.mobile-nav a[href]'); if (!a) return;
      const u = new URL(a.href, location.href); if (u.pathname !== path) return;
      e.preventDefault(); const box = $('#box');
      if (box) box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' }); else window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  // 18. Ночной фильтр — включается вечером
  safe('night', () => {
    if (!P.night_filter) return;
    const tick = () => { const h = new Date().getHours(); document.documentElement.classList.toggle('night-on', h >= 20 || h < 7); };
    tick(); setInterval(tick, 300000);
  });

  // 19. Код-пароль на приложение (хранится только на этом устройстве)
  async function sha(s) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode('nuvora-pin:' + s)); return Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2, '0')).join(''); }
  safe('applock', () => {
    if (!APP.user || !window.crypto || !crypto.subtle) return;
    const KEY = 'nv_pin_' + APP.user;
    const lockedNeeded = () => { const h = ls.get(KEY, ''); if (!h) return false; const t = +(sessionStorage.getItem('nv_unlock') || 0); return Date.now() - t > 60000; };
    function lock() {
      if ($('#nv-lock')) return;
      const el = document.createElement('div'); el.id = 'nv-lock'; el.innerHTML = `<div class="lock-box"><img src="/static/icon-192.png" alt=""><b>Введите код-пароль</b><div class="pin-dots"><i></i><i></i><i></i><i></i></div><div class="pin-pad">${[1, 2, 3, 4, 5, 6, 7, 8, 9, '', 0, '⌫'].map(n => `<button type="button" data-n="${n}"${n === '' ? ' disabled' : ''}>${n}</button>`).join('')}</div><form method="post" action="/logout"><button class="btn ghost sm">Забыли код? Выйти</button></form></div>`;
      document.body.appendChild(el); document.documentElement.classList.add('nv-locked');
      let code = '';
      const dots = () => $$('.pin-dots i', el).forEach((d, i) => d.classList.toggle('on', i < code.length));
      const press = async (n) => {
        if (n === '⌫') code = code.slice(0, -1); else if (code.length < 4) code += n;
        dots(); if (code.length < 4) return;
        if (await sha(code) === ls.get(KEY, '')) { try { sessionStorage.setItem('nv_unlock', Date.now()); } catch (e) { /* без сессии */ } el.remove(); document.documentElement.classList.remove('nv-locked'); }
        else { el.classList.add('shake'); vib(80); setTimeout(() => { el.classList.remove('shake'); code = ''; dots(); }, 450); }
      };
      el.addEventListener('click', e => { const b = e.target.closest('[data-n]'); if (b && b.dataset.n !== '') press(b.dataset.n); });
      document.addEventListener('keydown', function k(e) { if (!document.body.contains(el)) return document.removeEventListener('keydown', k); if (/^\d$/.test(e.key)) press(e.key); else if (e.key === 'Backspace') press('⌫'); });
    }
    if (lockedNeeded()) lock();
    let hiddenAt = 0;
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { hiddenAt = Date.now(); if (!$('#nv-lock')) try { sessionStorage.setItem('nv_unlock', Date.now()); } catch (e) { /* без сессии */ } }
      else if (hiddenAt && Date.now() - hiddenAt > 60000 && ls.get(KEY, '')) { try { sessionStorage.removeItem('nv_unlock'); } catch (e) { /* без сессии */ } lock(); }
    });
    // настройки код-пароля
    const box = $('#pin-settings'); if (!box) return;
    const state = $('#pin-state', box);
    const refresh = () => { const has = !!ls.get(KEY, ''); state.textContent = has ? 'Включён на этом устройстве' : 'Выключен'; $('#pin-off', box).classList.toggle('hidden', !has); };
    refresh();
    $('#pin-set', box).onclick = async () => {
      const a = prompt('Придумайте код из 4 цифр'); if (a === null) return;
      if (!/^\d{4}$/.test(a)) return toast('Нужно ровно 4 цифры', true);
      if (prompt('Повторите код') !== a) return toast('Коды не совпали', true);
      ls.set(KEY, await sha(a)); try { sessionStorage.setItem('nv_unlock', Date.now()); } catch (e) { /* без сессии */ } refresh(); toast('Код-пароль включён');
    };
    $('#pin-off', box).onclick = () => { if (confirm('Выключить код-пароль на этом устройстве?')) { ls.del(KEY); refresh(); toast('Код-пароль выключен'); } };
  });

  // 20. Очистить кэш приложения
  document.addEventListener('click', async e => {
    if (!e.target.closest('[data-clear-cache]')) return;
    try { if (window.caches) for (const k of await caches.keys()) await caches.delete(k); } catch (er) { /* нет кэша */ }
    ['nv_chat_tab', 'composer-draft', 'nv_search_hist'].forEach(ls.del);
    Object.keys(localStorage || {}).filter(k => k.startsWith('nv_draft_') || k.startsWith('nv_time_') || k.startsWith('nv_cdraft_')).forEach(ls.del);
    toast('Кэш очищен'); setTimeout(() => location.reload(), 700);
  });
  // размер сохранённого на устройстве — в настройках рядом с кнопкой
  safe('cache-size', () => {
    const el = $('[data-cache-size]'); if (!el || !navigator.storage || !navigator.storage.estimate) return;
    navigator.storage.estimate().then(s => { const mb = (s.usage || 0) / 1048576; el.textContent = 'Сейчас занято: ' + (mb < 1 ? '< 1' : mb.toFixed(1)) + ' МБ'; }).catch(() => {});
  });

  // ======================================================================== ЛЕНТА И ПОСТЫ
  // 21. «Есть новые посты»
  safe('newposts', () => {
    if (path !== '/' || !APP.user || !on('feed_new_pill')) return;
    const ids = $$('article.post[id^="post-"]').map(a => +a.id.slice(5)).filter(Boolean); if (!ids.length) return;
    const top = Math.max(...ids), tab = new URLSearchParams(location.search).get('tab') || '';
    const pill = document.createElement('button'); pill.type = 'button'; pill.className = 'new-pill hidden'; document.body.appendChild(pill);
    pill.onclick = () => { ls.del('nv_feed_scroll'); location.href = '/?tab=following'; };
    const check = async () => {
      if (document.hidden) return;
      try { const r = await (await fetch('/api/feed/new?after=' + top, { headers: { 'X-Requested-With': 'fetch' } })).json();
        if (r.ok && r.count) { pill.innerHTML = IC('back') + ' ' + (r.count > 9 ? '9+' : r.count) + ' ' + (r.count === 1 ? 'новый пост' : r.count < 5 ? 'новых поста' : 'новых постов'); pill.classList.remove('hidden'); } } catch (e) { /* нет сети */ }
    };
    setInterval(check, 60000); setTimeout(check, 20000);
    void tab;
  });

  // 22. Запоминать место в ленте
  safe('keepscroll', () => {
    if (path !== '/' || !on('feed_keep_scroll')) return;
    const k = 'nv_feed_scroll' + location.search;
    document.addEventListener('click', e => { if (e.target.closest('a[href^="/post/"], a[href^="/profile/"]')) try { sessionStorage.setItem(k, JSON.stringify({ y: scrollY, t: Date.now() })); } catch (er) { /* без сессии */ } }, true);
    try { const s = JSON.parse(sessionStorage.getItem(k) || 'null'); if (s && Date.now() - s.t < 15 * 60000) { sessionStorage.removeItem(k); requestAnimationFrame(() => { if (document.body.scrollHeight > s.y + 200) scrollTo(0, s.y); }); } } catch (e) { /* без сессии */ }
  });

  // 23. Прогресс чтения поста
  safe('progress', () => {
    if (!path.startsWith('/post/') || !on('reading_progress')) return;
    const bar = document.createElement('div'); bar.className = 'read-progress'; document.body.appendChild(bar);
    const upd = () => { const h = document.documentElement.scrollHeight - innerHeight; bar.style.width = (h > 0 ? Math.min(100, scrollY / h * 100) : 0) + '%'; };
    addEventListener('scroll', upd, { passive: true }); upd();
  });

  // 24. Прослушать пост (синтез речи)
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-tts]'); if (!b) return;
    if (!window.speechSynthesis) return toast('Озвучка не поддерживается на этом устройстве', true);
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); b.classList.remove('on'); return; }
    const t = document.getElementById(b.dataset.tts); if (!t) return;
    const u = new SpeechSynthesisUtterance(t.innerText.replace(/#/g, ' ')); u.lang = 'ru-RU'; u.rate = 1;
    const ru = speechSynthesis.getVoices().find(v => /^ru/i.test(v.lang)); if (ru) u.voice = ru;
    u.onend = () => b.classList.remove('on'); b.classList.add('on'); speechSynthesis.speak(u);
  });
  addEventListener('pagehide', () => { try { window.speechSynthesis && speechSynthesis.cancel(); } catch (e) { /* нет озвучки */ } });

  // 25. Размер текста поста A− / A+ (режим чтения)
  safe('readsize', () => {
    const root = document.documentElement; const k = 'nv_read_size';
    const apply = (v) => root.style.setProperty('--read-scale', v);
    apply(+ls.get(k, 1) || 1);
    document.addEventListener('click', e => { const b = e.target.closest('[data-readsize]'); if (!b) return; let v = (+ls.get(k, 1) || 1) + (b.dataset.readsize === '+' ? 0.1 : -0.1); v = Math.round(Math.max(0.8, Math.min(1.6, v)) * 10) / 10; ls.set(k, v); apply(v); toast('Размер текста: ' + Math.round(v * 100) + '%'); });
  });

  // 26. Поделиться постом как картинкой
  function wrap(ctx, text, maxW) { const out = []; for (const para of text.split('\n')) { let line = ''; for (const w of para.split(/\s+/)) { const t = line ? line + ' ' + w : w; if (ctx.measureText(t).width > maxW && line) { out.push(line); line = w; } else line = t; } out.push(line); } return out; }
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-quote-img]'); if (!b) return;
    const text = (document.getElementById(b.dataset.quoteImg) || {}).innerText || ''; if (!text.trim()) return toast('В посте нет текста', true);
    const W = 1080, H = 1350, c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d');
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, '#244f6b'); g.addColorStop(1, '#2f6487'); x.fillStyle = g; x.fillRect(0, 0, W, H);
    x.fillStyle = 'rgba(255,255,255,.12)'; x.beginPath(); x.arc(W - 120, 140, 260, 0, 7); x.fill();
    x.fillStyle = '#fff'; let size = 64; x.font = `700 ${size}px system-ui, sans-serif`;
    let lines = wrap(x, text.trim().slice(0, 600), W - 180);
    while (lines.length * size * 1.3 > H - 420 && size > 30) { size -= 4; x.font = `700 ${size}px system-ui, sans-serif`; lines = wrap(x, text.trim().slice(0, 600), W - 180); }
    const startY = Math.max(220, (H - lines.length * size * 1.3) / 2); lines.forEach((l, i) => x.fillText(l, 90, startY + i * size * 1.3));
    x.font = '600 40px system-ui, sans-serif'; x.fillStyle = 'rgba(255,255,255,.9)'; x.fillText(b.dataset.author || '', 90, H - 120);
    x.font = '800 44px system-ui, sans-serif'; x.textAlign = 'right'; x.fillText('Nuvora', W - 90, H - 120);
    c.toBlob(async blob => {
      const file = new File([blob], 'nuvora-post.png', { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [file] })) { try { await navigator.share({ files: [file] }); return; } catch (er) { /* отменили */ } }
      if (window.NuvoraApp && NuvoraApp.saveImage) {  // в приложении для Android ссылки blob: не скачиваются — сохраняет само приложение
        const r = new FileReader(); r.onload = () => { if (!NuvoraApp.saveImage(String(r.result), 'nuvora-post.png')) toast('Не удалось сохранить', true); }; r.readAsDataURL(blob); return;
      }
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'nuvora-post.png'; a.click(); toast('Картинка сохранена');
    }, 'image/png');
  });

  // 27. Копировать текст поста
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-copytext]'); if (!b) return;
    const t = document.getElementById(b.dataset.copytext); if (t && navigator.clipboard) navigator.clipboard.writeText(t.innerText).then(() => toast('Текст скопирован'));
  });

  // 28. Печать / сохранение в PDF
  document.addEventListener('click', e => { if (e.target.closest('[data-print]')) window.print(); });

  // 29. Картинка в картинке для видео + 30. громкость запоминается
  safe('video', () => {
    const vol = +ls.get('nv_vol', 1);
    const prep = (v) => { if (v.dataset.nvv) return; v.dataset.nvv = 1; if (!isNaN(vol)) v.volume = vol; v.addEventListener('volumechange', () => ls.set('nv_vol', v.volume));
      if (v.closest('.post') && !v.closest('.has-circle')) {  // скорость 1× / 1,5× / 2×
        const sp = document.createElement('button'); sp.type = 'button'; sp.className = 'speed-btn'; sp.textContent = '1×'; sp.title = 'Скорость';
        sp.onclick = (e) => { e.preventDefault(); e.stopPropagation(); const r = v.playbackRate >= 2 ? 1 : v.playbackRate >= 1.5 ? 2 : 1.5; v.playbackRate = r; sp.textContent = String(r).replace('.', ',') + '×'; };
        const p0 = v.parentElement; if (p0) { if (getComputedStyle(p0).position === 'static') p0.style.position = 'relative'; p0.appendChild(sp); }
      }
      if (document.pictureInPictureEnabled && v.closest('.post') && !v.closest('.has-circle')) { const b = document.createElement('button'); b.type = 'button'; b.className = 'pip-btn'; b.title = 'Картинка в картинке'; b.innerHTML = IC('layers'); b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); v.requestPictureInPicture().catch(() => toast('Не удалось открыть', true)); }; const p = v.parentElement; if (p && getComputedStyle(p).position === 'static') p.style.position = 'relative'; p && p.appendChild(b); } };
    $$('video').forEach(prep);
    if (window.MutationObserver) new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) (n.tagName === 'VIDEO' ? [n] : $$('video', n)).forEach(prep); }))).observe(document.body, { childList: true, subtree: true });
  });

  // 31. Подсветка упоминаний меня
  safe('mentions', () => {
    if (!APP.user) return;
    const mark = (r) => $$('a[href="/profile/' + APP.user + '"]', r).forEach(a => { if (a.closest('.post-text, .comment-text, .txt, .c-text')) a.classList.add('me-mention'); });
    mark(document);
  });

  // 32. Переход к комментарию по ссылке с подсветкой
  safe('hash', () => {
    if (!location.hash || location.hash.length < 2) return;
    const t = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (!t) return;
    setTimeout(() => { t.scrollIntoView({ block: 'center' }); t.classList.add('flash'); setTimeout(() => t.classList.remove('flash'), 2200); }, 200);
  });

  // 33. Черновик комментария сохраняется
  safe('cdraft', () => {
    const f = $('#comment-form'); if (!f) return; const ta = $('[name=content]', f); if (!ta) return;
    const k = 'nv_cdraft_' + path; const d = ls.get(k, ''); if (d && !ta.value) ta.value = d;
    ta.addEventListener('input', () => ta.value.trim() ? ls.set(k, ta.value) : ls.del(k));
    f.addEventListener('submit', () => ls.del(k));
  });

  // 34. Ctrl+Enter — отправить комментарий / пост
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || !(e.ctrlKey || e.metaKey)) return;
    const f = e.target.closest && e.target.closest('#comment-form, #composer, form.comment-form'); if (!f) return;
    e.preventDefault(); f.requestSubmit ? f.requestSubmit() : f.submit();
  });

  // 35. Не потерять пост: предупреждение при уходе
  safe('unsaved', () => {
    const f = $('#composer'); if (!f || path !== '/create') return; let sending = false;
    f.addEventListener('submit', () => { sending = true; });
    addEventListener('beforeunload', e => { const t = $('textarea[name=content]', f); if (!sending && t && t.value.trim().length > 20) { e.preventDefault(); e.returnValue = ''; } });
  });

  // 36. Перетаскивание фото в редактор поста
  safe('drop', () => {
    const f = $('#composer'), input = $('#composer-files'); if (!f || !input || !window.DataTransfer) return;
    f.addEventListener('dragover', e => { e.preventDefault(); f.classList.add('drag'); });
    f.addEventListener('dragleave', () => f.classList.remove('drag'));
    f.addEventListener('drop', e => { e.preventDefault(); f.classList.remove('drag'); const dt = new DataTransfer(); for (const file of e.dataTransfer.files) if (/^(image|video)\//.test(file.type)) dt.items.add(file); if (!dt.files.length) return; input.files = dt.files; input.dispatchEvent(new Event('change')); });
  });

  // 37. История поиска и 38. подсветка совпадений
  safe('search', () => {
    if (path !== '/search') return;
    const q = new URLSearchParams(location.search).get('q') || '';
    let hist = []; try { hist = JSON.parse(ls.get('nv_search_hist', '[]')) || []; } catch (e) { hist = []; }
    if (q.trim()) { hist = [q.trim()].concat(hist.filter(h => h !== q.trim())).slice(0, 10); ls.set('nv_search_hist', JSON.stringify(hist)); }
    const inp = $('main input[name=q], .content input[name=q], form[action="/search"] input[name=q]');
    if (inp && hist.length && !q) {
      const box = document.createElement('div'); box.className = 'card search-hist';
      box.innerHTML = '<div class="card-title">' + IC('history') + ' Вы искали <button type="button" class="btn ghost sm" data-hclear>Очистить</button></div><div class="chips">' + hist.map(h => `<a class="chip" href="/search?q=${encodeURIComponent(h)}">${esc(h)}</a>`).join('') + '</div>';
      (inp.closest('form') || inp).after(box);
      $('[data-hclear]', box).onclick = () => { ls.del('nv_search_hist'); box.remove(); };
    }
    if (q.trim().length >= 2) {
      const rx = new RegExp('(' + q.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
      $$('.post-text, .user-row .info, .search-results .bio').forEach(el => {
        const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
        nodes.forEach(n => { if (!rx.test(n.nodeValue)) return; rx.lastIndex = 0; const s = document.createElement('span'); s.innerHTML = esc(n.nodeValue).replace(rx, '<mark>$1</mark>'); n.replaceWith(s); });
      });
    }
  });

  // ======================================================================== ПРОФИЛЬ И ГЛАВНАЯ
  // 39. Поделиться профилем, 40. копировать @логин
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-share-profile]'); if (b) {
      const url = location.origin + '/profile/' + b.dataset.shareProfile;
      if (navigator.share) { try { await navigator.share({ title: document.title, url }); return; } catch (er) { /* отменили */ } }
      if (navigator.clipboard) { await navigator.clipboard.writeText(url); toast('Ссылка на профиль скопирована'); }
      return;
    }
    const u = e.target.closest('[data-copy-username]');
    if (u && navigator.clipboard) navigator.clipboard.writeText('@' + u.dataset.copyUsername).then(() => toast('@' + u.dataset.copyUsername + ' скопирован'));
  });

  // 41. Приветствие по времени суток + совет дня, 42. поздравление в свой день рождения
  safe('greeting', () => {
    if (path !== '/' || !APP.user || !on('greeting')) return;
    const anchor = $('.tabs'); if (!anchor) return;
    const h = new Date().getHours(), part = h < 5 ? 'Доброй ночи' : h < 12 ? 'Доброе утро' : h < 18 ? 'Добрый день' : 'Добрый вечер';
    const today = localDate().slice(5), bday = APP.bday && APP.bday === today;
    const TIPS = ['Нажмите Ctrl+K, чтобы быстро перейти в любой раздел.', 'Зажмите сообщение и нажмите звёздочку — оно попадёт в «Избранное».', 'В чате можно поставить свой фон: меню ⋯ → «Оформление».',
      'Запишите контакт по-своему: в профиле нажмите ⋯ → «Записать как…».', 'Зажмите «Отправить», чтобы отправить сообщение позже или без звука.', 'Код-пароль на приложение — в настройках безопасности.',
      'Напишите /roll в чате — и бросьте кубик.', 'Забыли переключить раскладку? Nuvora предложит исправить «ghbdtn» на «привет».', 'Потяните ленту вниз, чтобы обновить её.',
      'Кнопка «Прослушать» на странице поста прочитает его вслух.', 'Посмотрите, у кого скоро день рождения: Меню → Дни рождения.', 'Включите «Экономию трафика» в настройках ленты для мобильного интернета.'];
    const tip = TIPS[Math.floor(Date.now() / 86400000) % TIPS.length];
    const tcard = $('#today-card');
    if (tcard) {  // одна карточка «Сегодня»: приветствие, совет, сундук и «Что нового»
      $('#today-hi', tcard).textContent = bday ? 'С днём рождения, ' + ((APP.name || '').split(' ')[0] || APP.user) + '!' : part + ', ' + ((APP.name || '').split(' ')[0] || APP.user) + '!';
      $('#today-tip', tcard).innerHTML = bday ? 'Вся команда Nuvora желает вам счастья. Сегодня ваш день!' : IC('bulb') + ' ' + esc(tip);
      if (bday) tcard.classList.add('bday');
      if (bday && ls.get('nv_confetti', '') !== localDate().slice(5)) { ls.set('nv_confetti', localDate().slice(5)); confetti(); }
      return;
    }
    const k = 'nv_greet_' + localDate(); if (ls.get(k, '') === 'x') return;
    const card = document.createElement('div'); card.className = 'card greet' + (bday ? ' bday' : '');
    card.innerHTML = `<button type="button" class="icon-btn greet-x" title="Скрыть на сегодня">${IC('x')}</button><b>${bday ? 'С днём рождения, ' + esc(APP.name || APP.user) + '!' : part + ', ' + esc(APP.name || APP.user) + '!'}</b><div class="small muted">${bday ? 'Вся команда Nuvora желает вам счастья. Сегодня ваш день!' : IC('bulb') + ' ' + esc(tip)}</div>`;
    anchor.before(card); $('.greet-x', card).onclick = () => { ls.set(k, 'x'); card.remove(); };
    if (bday && ls.get('nv_confetti', '') !== today) { ls.set('nv_confetti', today); confetti(); }
  });
  function confetti() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const c = document.createElement('canvas'); c.className = 'confetti'; c.width = innerWidth; c.height = innerHeight; document.body.appendChild(c); const x = c.getContext('2d');
    const cols = ['#2f6487', '#c2552f', '#c98a1b', '#3c9a5f', '#1f1d1a']; const ps = Array.from({ length: 140 }, () => ({ x: Math.random() * c.width, y: -20 - Math.random() * c.height * 0.5, r: 4 + Math.random() * 5, vy: 2 + Math.random() * 3, vx: -1 + Math.random() * 2, a: Math.random() * 6, c: cols[Math.floor(Math.random() * cols.length)] }));
    let t = 0; (function f() { x.clearRect(0, 0, c.width, c.height); ps.forEach(p => { p.y += p.vy; p.x += p.vx; p.a += 0.1; x.save(); x.translate(p.x, p.y); x.rotate(p.a); x.fillStyle = p.c; x.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); x.restore(); }); if (++t < 260) requestAnimationFrame(f); else c.remove(); })();
  }
  window.NV.confetti = confetti;

  // ======================================================================== ЧАТЫ
  // 43. Команды в чате, 44. звук отправки, 45. исправление раскладки при отправке не трогаем — только подсказка
  const COMMANDS = {
    '/shrug': () => '¯\\_(ツ)_/¯', '/tableflip': () => '(╯°□°)╯︵ ┻━┻', '/unflip': () => '┬─┬ノ( º _ ºノ)', '/lenny': () => '( ͡° ͜ʖ ͡°)',
    '/roll': (a) => { const n = Math.max(2, Math.min(1000, parseInt(a, 10) || 6)); return '🎲 Бросаю кубик (1–' + n + '): выпало ' + (1 + Math.floor(Math.random() * n)); },
    '/coin': () => '🪙 Монетка: ' + (Math.random() < 0.5 ? 'орёл' : 'решка'), '/flip': () => '🪙 Монетка: ' + (Math.random() < 0.5 ? 'орёл' : 'решка'),
    '/8ball': () => '🎱 ' + ['Да', 'Нет', 'Скорее да', 'Скорее нет', 'Спроси позже', 'Без сомнений', 'Даже не думай', 'Знаки говорят — да'][Math.floor(Math.random() * 8)],
    '/time': () => '🕒 У меня сейчас ' + new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
  };
  function sendSound() { try { const c = new AudioContext(), o = c.createOscillator(), g = c.createGain(); o.type = 'sine'; o.connect(g); g.connect(c.destination); o.frequency.setValueAtTime(520, c.currentTime); o.frequency.exponentialRampToValueAtTime(980, c.currentTime + 0.12); g.gain.setValueAtTime(0.06, c.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + 0.18); o.start(); o.stop(c.currentTime + 0.2); } catch (e) { /* без звука */ } }
  function transformOutgoing(text) {
    if (!on('chat_commands')) return text;
    const m = text.match(/^(\/[a-z0-9]+)(?:\s+(.*))?$/i);
    if (m && COMMANDS[m[1].toLowerCase()]) return COMMANDS[m[1].toLowerCase()](m[2] || '');
    return text;
  }
  window.NV.transformOutgoing = transformOutgoing; window.NV.COMMANDS = COMMANDS;
  safe('sendwrap', () => {
    if (typeof window.sendText !== 'function') return;
    const orig = window.sendText;
    window.sendText = async function (text) { const t = transformOutgoing(text); if (P.send_sound) sendSound(); vib(8); return orig.call(this, t); };
  });

  // 46. Черновики в списке чатов, 47. свайп влево — в архив
  safe('chatlist', () => {
    const list = $('#chat-list'); if (!list) return;
    $$('.chat[data-uid]', list).forEach(row => {
      const d = ls.get('nv_draft_' + row.dataset.uid, ''); if (!d) return;
      const pv = $('.preview', row); if (pv) { pv.innerHTML = '<span class="draft-tag">Черновик:</span> ' + esc(d.slice(0, 80)); pv.classList.add('has-draft'); }
    });
    if (!('ontouchstart' in window)) return;
    let row = null, x0 = 0, y0 = 0, dx = 0;
    list.addEventListener('touchstart', e => { row = e.target.closest('.chat[data-user]'); if (!row) return; x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; }, { passive: true });
    list.addEventListener('touchmove', e => { if (!row) return; dx = e.touches[0].clientX - x0; if (Math.abs(e.touches[0].clientY - y0) > 25) { row.style.transform = ''; row = null; return; } if (dx < 0) { row.style.transform = `translateX(${Math.max(dx, -110)}px)`; row.classList.toggle('swipe-arch', dx < -80); } }, { passive: true });
    list.addEventListener('touchend', async () => {
      if (!row) return; const r = row; row = null; r.style.transition = 'transform .2s'; r.style.transform = ''; setTimeout(() => { r.style.transition = ''; r.classList.remove('swipe-arch'); }, 220);
      if (dx < -80) { vib(12); try { const res = await App.api(`/chats/${r.dataset.user}/archive`); r.remove(); toast(res.archived ? 'Чат в архиве' : 'Чат возвращён из архива'); } catch (e) { /* ошибка показана */ } }
    });
  });

  // 48. «Прочитать все» в списке чатов
  document.addEventListener('click', async e => {
    if (!e.target.closest('[data-read-all-chats]')) return;
    try { const r = await App.api('/messages/read-all'); toast(r.count ? 'Прочитано сообщений: ' + r.count : 'Непрочитанных нет'); setTimeout(() => location.reload(), 500); } catch (er) { /* ошибка показана */ }
  });

  // 50. Выход из аккаунта: отписываем push этого браузера и стираем кэш фото — на общем компьютере ничего не останется
  document.addEventListener('submit', e => {
    const f = e.target; if (e.defaultPrevented || !f.matches || !f.matches('form[action="/logout"]') || f.dataset.clean) return;
    e.preventDefault(); f.dataset.clean = 1;
    const done = () => f.submit();
    const tasks = [];
    try { if (window.caches) tasks.push(caches.delete('media-v1'), caches.delete('pages-v1')); } catch (er) { /* нет кэша */ }
    ls.del('nv_saved_pages');
    try { sessionStorage.removeItem('nv_unlock'); } catch (er) { /* без сессии */ }
    ls.del('nv_push_ep');
    if (navigator.serviceWorker && window.PushManager) tasks.push(navigator.serviceWorker.getRegistration().then(reg => reg && reg.pushManager.getSubscription()).then(sub => {
      if (!sub) return; const ep = sub.endpoint;
      return fetch('/api/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' }, body: JSON.stringify({ endpoint: ep }) }).catch(() => {}).then(() => sub.unsubscribe());
    }).catch(() => {}));
    Promise.race([Promise.all(tasks), new Promise(r => setTimeout(r, 1500))]).then(done, done);
  });

  // 51. Черновики в групповых чатах
  safe('gdraft', () => {
    const g = $('#ginp'); if (!g) return; const k = 'nv_draft_g' + path;
    const d = ls.get(k, ''); if (d && !g.value) g.value = d;
    g.addEventListener('input', () => g.value.trim() ? ls.set(k, g.value) : ls.del(k));
    const f = g.closest('form'); if (f) f.addEventListener('submit', () => ls.del(k), true);
    document.addEventListener('keydown', e => { if (e.target === g && e.key === 'Enter' && !e.shiftKey) setTimeout(() => { if (!g.value.trim()) ls.del(k); }, 50); });
  });

  // 52. Уведомления: смахните влево, чтобы удалить
  safe('notifswipe', () => {
    if (path !== '/notifications' || !('ontouchstart' in window)) return;
    let row = null, x0 = 0, y0 = 0, dx = 0;
    document.addEventListener('touchstart', e => { row = e.target.closest('[id^="n-"]'); if (!row) return; x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; dx = 0; }, { passive: true });
    document.addEventListener('touchmove', e => { if (!row) return; dx = e.touches[0].clientX - x0; if (Math.abs(e.touches[0].clientY - y0) > 25) { row.style.transform = ''; row = null; return; } row.style.transform = `translateX(${Math.max(-140, Math.min(dx, 100))}px)`; if (dx < 0) row.style.opacity = 1 + dx / 300; }, { passive: true });
    document.addEventListener('touchend', async () => {
      if (!row) return; const r = row; row = null; const id = r.id.slice(2);
      if (dx > 90 && /^\d+$/.test(id)) { vib(8); r.style.transition = 'transform .2s'; r.style.transform = ''; r.style.background = ''; try { await App.api(`/notifications/${id}/read`); toast('Отмечено прочитанным'); } catch (e) { /* ошибка показана */ } return; }
      if (dx < -110 && /^\d+$/.test(id)) { vib(12); r.style.transition = 'transform .2s, opacity .2s'; r.style.transform = 'translateX(-100%)'; r.style.opacity = 0; try { await App.api(`/notifications/${id}/delete`); } catch (e) { /* ошибка показана */ } setTimeout(() => r.remove(), 200); }
      else { r.style.transition = 'transform .2s'; r.style.transform = ''; r.style.opacity = ''; setTimeout(() => { r.style.transition = ''; }, 220); }
    });
  });

  // ======================================================================== ЧТО НОВОГО
  // 49. Баннер «Что нового» один раз после обновления
  safe('whatsnew', () => {
    if (!APP.user || path === '/whats-new' || !APP.version) return;
    if (ls.get('nv_seen_version', '') === APP.version) return;
    if (!ls.get('nv_seen_version', '') && !$('article.post')) { ls.set('nv_seen_version', APP.version); return; }
    if (path !== '/') return;
    const today = $('#today-card .today-main');
    if (today) {
      const a = document.createElement('a'); a.href = '/whats-new'; a.className = 'today-new';
      a.innerHTML = `${IC('sparkle')} Что нового в Nuvora ${esc(APP.version)}`; a.onclick = () => ls.set('nv_seen_version', APP.version);
      today.appendChild(a); return;
    }
    const anchor = $('.tabs'); if (!anchor) return;
    const card = document.createElement('a'); card.href = '/whats-new'; card.className = 'card whatsnew-card';
    card.innerHTML = `${IC('sparkle')}<div class="grow"><b>Что нового в Nuvora ${esc(APP.version)}</b><div class="small muted">Посмотрите, что появилось в обновлении</div></div>${IC('back')}`;
    card.onclick = () => ls.set('nv_seen_version', APP.version);
    anchor.before(card);
  });
  if (path === '/whats-new' && APP.version) ls.set('nv_seen_version', APP.version);
})();

// Поле «Город»: подсказки из справочника населённых пунктов России
(function () {
  document.querySelectorAll('input[data-places]').forEach(function (inp) {
    var list = document.getElementById(inp.getAttribute('list')), timer, last = '';
    if (!list) return;
    inp.addEventListener('input', function () {
      clearTimeout(timer);
      var q = inp.value.trim();
      if (q.length < 2 || q === last) return;
      timer = setTimeout(function () {
        last = q;
        fetch('/api/places?q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
          list.innerHTML = '';
          (d.items || []).forEach(function (label) { var o = document.createElement('option'); o.value = label; list.appendChild(o); });
        }).catch(function () {});
      }, 250);
    });
  });
})();
