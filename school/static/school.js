/* Школа: небольшие помощники — запросы, всплывающие подсказки, окна, отметка заданий, чат. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  function toast(t) { const el = $('#toast'); if (!el) return; el.textContent = t; el.classList.add('show'); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('show'), 2200); }
  async function api(url, data, method) {
    const opt = { method: method || (data ? 'POST' : 'GET'), headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' };
    if (data) { const fd = new FormData(); for (const k in data) fd.append(k, data[k]); opt.body = fd; }
    const r = await fetch(url, opt); let j = {};
    try { j = await r.json(); } catch (e) {}
    if (r.status === 401) { location.href = '/login'; throw new Error('auth'); }
    if (!r.ok || j.ok === false) { toast(j.error || 'Ошибка'); throw new Error(j.error || 'err'); }
    return j;
  }
  window.School = { api, toast };

  // окна: <button data-open="id">, <div class="sheet" id="id">
  document.addEventListener('click', e => {
    const o = e.target.closest('[data-open]');
    if (o) { const s = document.getElementById(o.dataset.open); if (s) { s.classList.add('open'); s.dispatchEvent(new CustomEvent('open', { detail: o })); } return; }
    const sh = e.target.closest('.sheet');
    if (sh && (e.target === sh || e.target.closest('[data-close]'))) sh.classList.remove('open');
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') $$('.sheet.open').forEach(s => s.classList.remove('open')); });

  // подтверждение опасных действий
  document.addEventListener('submit', e => { const f = e.target; if (f.dataset.confirm && !confirm(f.dataset.confirm)) e.preventDefault(); });

  // ученик отмечает задание выполненным
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-done]'); if (!b) return;
    e.preventDefault();
    try { const r = await api(`/s/homework/${b.dataset.done}/done`, {}); b.closest('.hw-item').classList.toggle('done', r.done); toast(r.done ? 'Отмечено как сделанное' : 'Снята отметка'); } catch (er) {}
  });

  // переписка
  const box = $('#msgs');
  if (box) {
    const url = box.dataset.api; let last = 0, meTeacher = null, readUpto = 0;
    const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
    const draw = (msgs) => {
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
      for (const x of msgs) {
        if ($(`[data-mid="${x.id}"]`, box)) continue;
        const me = x.mine_t === meTeacher;
        const el = document.createElement('div'); el.className = 'm' + (me ? ' me' : ''); el.dataset.mid = x.id;
        el.innerHTML = esc(x.text) + `<small>${x.at}${me ? ' <span class="rd"></span>' : ''}</small>`;
        box.appendChild(el); last = Math.max(last, x.id);
      }
      $('.empty', box)?.remove();
      if (!box.querySelector('.m')) box.innerHTML = '<div class="empty">Сообщений пока нет — напишите первым</div>';
      $$('.m.me', box).forEach(el => { const r = $('.rd', el); if (r) r.textContent = +el.dataset.mid <= readUpto ? '· прочитано' : ''; });
      if (atBottom || msgs.length) box.scrollTop = box.scrollHeight;
    };
    const poll = async () => { try { const r = await api(url + '?after=' + last); meTeacher = r.me_teacher; readUpto = r.read_upto; draw(r.messages); } catch (e) {} };
    poll(); setInterval(() => { if (!document.hidden) poll(); }, 3000);
    const ta = $('#msg-text'), send = async () => {
      const t = ta.value.trim(); if (!t) return; ta.value = ''; ta.style.height = '';
      try { const r = await api(url, { text: t }); draw([r.message]); } catch (e) { ta.value = t; }
    };
    $('#msg-send').onclick = send;
    ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !('ontouchstart' in window)) { e.preventDefault(); send(); } });
    ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(140, ta.scrollHeight) + 'px'; });
  }

  // журнал: окно добавления оценки
  const gs = $('#grade-sheet');
  if (gs) {
    gs.addEventListener('open', e => {
      const b = e.detail; $('[name=subject]', gs).value = b.dataset.subject; $('#gs-title', gs).textContent = b.dataset.name;
      $$('.pick button', gs).forEach(x => x.classList.remove('on')); $('[name=value]', gs).value = '';
    });
    $$('.pick button', gs).forEach(x => x.onclick = () => { $$('.pick button', gs).forEach(y => y.classList.remove('on')); x.classList.add('on'); $('[name=value]', gs).value = x.dataset.v; });
    $('form', gs).addEventListener('submit', e => { if (!$('[name=value]', gs).value) { e.preventDefault(); toast('Выберите оценку'); } });
  }
  // нажатие на оценку в журнале — подробности и удаление
  document.addEventListener('click', async e => {
    const g = e.target.closest('[data-grade]'); if (!g) return;
    const info = g.dataset.info;
    if (g.dataset.del && confirm(info + '\n\nУдалить эту оценку?')) { try { await api(`/t/grades/${g.dataset.grade}/delete`, {}); g.remove(); toast('Оценка удалена'); } catch (er) {} }
    else if (!g.dataset.del) toast(info);
  });

  // домашнее задание: срок по умолчанию — ближайший урок этого предмета
  const hs = $('#hw-subject');
  if (hs) hs.addEventListener('change', () => { const d = JSON.parse(hs.dataset.due || '{}')[hs.value]; if (d) $('#hw-due').value = d; });

  // счётчик новых сообщений в меню обновляется сам
  const badgeUpdate = async () => {
    if (document.hidden || box) return;
    try { const r = await fetch('/api/updates', { headers: { 'X-Requested-With': 'fetch' } }).then(r => r.json()); $$('[data-unread]').forEach(b => { b.textContent = r.messages || ''; b.hidden = !r.messages; }); } catch (e) {}
  };
  if ($('[data-unread]')) setInterval(badgeUpdate, 20000);
})();
