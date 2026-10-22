/* Звонки 1 на 1 (WebRTC). Видео и звук идут напрямую между собеседниками;
   сервер передаёт только сигналы: /v3/call/<логин>/start, /v3/call/<id>/signal и долгий запрос /v3/call/poll. */
(function () {
  'use strict';
  if (!window.APP || !APP.user) return;
  const TAB = Math.random().toString(36).slice(2, 10);
  const RING_MS = 45000;
  const HDR = { 'X-Requested-With': 'fetch', 'Content-Type': 'application/json', Accept: 'application/json' };
  const post = (url, d) => fetch(url, { method: 'POST', headers: HDR, credentials: 'same-origin', body: JSON.stringify(d || {}) })
    .then(r => r.json().catch(() => ({ ok: r.ok }))).catch(() => ({ ok: false, error: 'Нет связи с сервером' }));
  const say = (t, err) => (window.App && App.toast ? App.toast(t, err) : alert(t));
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const esc = s => String(s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const sprite = (() => { const u = document.querySelector('use[href*="icons.svg"]'); return u ? u.getAttribute('href').split('#')[0] : '/static/icons.svg'; })();
  const ico = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="${sprite}#${n}"/></svg>`;
  const awake = on => { try { window.NuvoraApp && NuvoraApp.keepAwake && NuvoraApp.keepAwake(on); } catch (e) {} }; // экран не гаснет в приложении
  const supported = () => !!(window.RTCPeerConnection && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  let ICE = null, since = -1, cur = null;
  const seen = new Set(); // звонки, которые эта вкладка уже показала

  // ------------------------------------------------------------------ звук вызова (без файлов: WebAudio)
  let actx = null, ringT = null;
  function tone(kind) {
    stopTone();
    try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); actx.resume && actx.resume(); } catch (e) { return; }
    const beep = (f1, f2, dur) => {
      const t = actx.currentTime, g = actx.createGain(); g.connect(actx.destination);
      g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(kind === 'in' ? .22 : .08, t + .03); g.gain.setValueAtTime(kind === 'in' ? .22 : .08, t + dur - .05); g.gain.linearRampToValueAtTime(0, t + dur);
      [f1, f2].forEach(f => { const o = actx.createOscillator(); o.frequency.value = f; o.connect(g); o.start(t); o.stop(t + dur); });
    };
    const play = () => { if (kind === 'in') { beep(784, 1046, .35); setTimeout(() => beep(784, 1046, .35), 450); } else beep(425, 425, 1); };
    play(); ringT = setInterval(play, kind === 'in' ? 2400 : 4000);
    if (kind === 'in' && navigator.vibrate) try { navigator.vibrate([600, 400, 600, 400, 600, 400, 600, 400, 600, 400, 600]); } catch (e) {}
  }
  function stopTone() { clearInterval(ringT); ringT = null; if (navigator.vibrate) try { navigator.vibrate(0); } catch (e) {} }

  // ------------------------------------------------------------------ экран звонка
  function ui(c) {
    const el = document.createElement('div');
    el.className = 'call-ui' + (c.video ? ' is-video' : ' is-audio');
    const av = c.peer.avatar ? `<img src="${esc(c.peer.avatar)}" alt="">` : `<span>${esc((c.peer.name || c.peer.username || '?')[0].toUpperCase())}</span>`;
    el.innerHTML = `<video class="call-remote" autoplay playsinline></video>
      <div class="call-peer"><div class="call-av">${av}</div><b>${esc(c.peer.name || c.peer.username)}</b><span class="call-st"></span></div>
      <video class="call-local" autoplay playsinline muted></video>
      <div class="call-ctl call-ctl-in">
        <button type="button" class="call-btn red" data-c="decline" title="Отклонить">${ico('phone')}<small>Отклонить</small></button>
        <button type="button" class="call-btn green" data-c="accept" title="Ответить">${ico(c.video ? 'video' : 'phone')}<small>Ответить</small></button>
      </div>
      <div class="call-ctl call-ctl-on">
        <button type="button" class="call-btn" data-c="mic" title="Микрофон">${ico('mic')}<small>Микрофон</small></button>
        ${c.video ? `<button type="button" class="call-btn" data-c="cam" title="Камера">${ico('video')}<small>Камера</small></button>
        <button type="button" class="call-btn" data-c="flip" title="Другая камера">${ico('refresh')}<small>Повернуть</small></button>` : ''}
        <button type="button" class="call-btn red" data-c="hangup" title="Завершить">${ico('phone')}<small>Завершить</small></button>
      </div>`;
    el.addEventListener('click', e => {
      const b = e.target.closest('[data-c]'); if (!b) return;
      ({ accept, decline: () => hangup('decline'), hangup: () => hangup('hangup'), mic: toggleMic, cam: toggleCam, flip })[b.dataset.c]();
    });
    document.body.appendChild(el);
    document.documentElement.classList.add('in-call');
    c.el = el; c.$ = s => el.querySelector(s);
    return el;
  }
  const status = t => { if (cur && cur.el) cur.$('.call-st').textContent = t; };
  function mode(m) { if (cur && cur.el) { cur.el.classList.toggle('incoming', m === 'incoming'); cur.el.classList.toggle('live', m !== 'incoming'); } }

  // ------------------------------------------------------------------ соединение
  async function media(video) {
    const a = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    try { return await navigator.mediaDevices.getUserMedia({ audio: a, video: video ? { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } } : false }); }
    catch (e) {
      if (video) try { const s = await navigator.mediaDevices.getUserMedia({ audio: a }); say('Камера недоступна — звонок без видео'); return s; } catch (e2) {}
      throw new Error(e && e.name === 'NotAllowedError' ? 'Разрешите доступ к микрофону' + (video ? ' и камере' : '') + ' для звонков' : 'Не удалось включить микрофон');
    }
  }
  async function ice() {
    if (!ICE) { try { ICE = (await (await fetch('/v3/call/ice', { headers: HDR, credentials: 'same-origin' })).json()).ice; } catch (e) {} }
    return ICE || [];
  }
  function peer(c) {
    const pc = new RTCPeerConnection({ iceServers: c.ice });
    c.local.getTracks().forEach(t => pc.addTrack(t, c.local));
    pc.onicecandidate = e => { if (e.candidate) { c.iceOut.push(e.candidate.toJSON ? e.candidate.toJSON() : e.candidate); flushIce(c); } };
    pc.ontrack = e => {
      const v = c.$('.call-remote');
      if (v.srcObject !== e.streams[0]) { v.srcObject = e.streams[0]; v.play && v.play().catch(() => {}); }
      if (e.track.kind === 'video') { c.el.classList.add('has-remote'); e.track.onmute = () => c.el.classList.remove('has-remote'); e.track.onunmute = () => c.el.classList.add('has-remote'); }
    };
    const onState = () => {
      const st = pc.connectionState || pc.iceConnectionState;
      if (st === 'connected' || st === 'completed') connected(c);
      else if (st === 'disconnected') { status('Связь прервалась, переподключаем…'); clearTimeout(c.lost); c.lost = setTimeout(() => cur === c && hangup('hangup', 'Связь потеряна'), 12000); }
      else if (st === 'failed') hangup('hangup', 'Не удалось соединиться. Проверьте интернет');
    };
    pc.onconnectionstatechange = onState; pc.oniceconnectionstatechange = onState;
    c.pc = pc;
    return pc;
  }
  function flushIce(c) {
    if (!c.id || !c.iceOut.length || c.iceT) return;
    c.iceT = setTimeout(() => { c.iceT = null; const list = c.iceOut.splice(0); if (list.length && cur === c) post(`/v3/call/${c.id}/signal`, { kind: 'ice', candidates: list, tab: TAB }); }, 150);
  }
  async function addIce(c, list) {
    for (const x of list) { try { await c.pc.addIceCandidate(x); } catch (e) {} }
  }
  function connected(c) {
    clearTimeout(c.lost); stopTone();
    if (c.t0) { status(''); return; }
    c.t0 = Date.now(); mode('live');
    const tick = () => { const s = Math.floor((Date.now() - c.t0) / 1000); status(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`); };
    tick(); c.clock = setInterval(tick, 1000);
    c.ping = setInterval(() => post(`/v3/call/${c.id}/signal`, { kind: 'ping' }), 20000);
    awake(true);
    try { navigator.wakeLock && navigator.wakeLock.request('screen').then(l => { c.lock = l; }).catch(() => {}); } catch (e) {}
  }

  // ------------------------------------------------------------------ исходящий звонок
  async function start(username, video, name, avatar) {
    if (cur) return say('Сначала завершите текущий звонок');
    if (!supported()) return say('Этот браузер не умеет звонить. Обновите его или откройте приложение Nuvora', true);
    const c = cur = { role: 'out', video, peer: { username, name: name || username, avatar }, iceOut: [], iceIn: [] };
    ui(c); mode('live'); status('Включаем ' + (video ? 'камеру…' : 'микрофон…'));
    try {
      c.local = await media(video);
      if (cur !== c) return c.local.getTracks().forEach(t => t.stop());
      c.$('.call-local').srcObject = c.local;
      c.ice = await ice();
      const pc = peer(c);
      await pc.setLocalDescription(await pc.createOffer());
      status('Вызываем…');
      const r = await post(`/v3/call/${encodeURIComponent(username)}/start`, { video: video ? 1 : 0, offer: { type: 'offer', sdp: pc.localDescription.sdp }, tab: TAB });
      if (cur !== c) { if (r.ok) post(`/v3/call/${r.call}/signal`, { kind: 'hangup' }); return; }
      if (!r.ok) { cleanup(); return say(r.error || 'Не удалось позвонить', true); }
      c.id = r.call; seen.add(c.id); if (r.peer) c.$('.call-peer b').textContent = r.peer.name;
      flushIce(c); tone('out');
      c.ringTo = setTimeout(() => { if (cur === c && !c.t0) hangup('hangup', 'Не отвечает'); }, RING_MS);
    } catch (e) { cleanup(); say(e.message || 'Не удалось позвонить', true); }
  }

  // ------------------------------------------------------------------ входящий звонок
  function incoming(e) {
    if (seen.has(e.call)) return;
    seen.add(e.call);
    if (cur) return; // в этой вкладке уже идёт разговор — сервер всё равно не даст двух звонков
    if (!supported()) { say(`${e.from.name} звонит вам, но этот браузер не умеет звонить`, true); return; }
    const c = cur = { role: 'in', id: e.call, video: !!e.video, peer: e.from, offer: e.offer, iceOut: [], iceIn: [] };
    ui(c); mode('incoming'); status(c.video ? 'Видеозвонок' : 'Звонок');
    tone('in');
    c.ringTo = setTimeout(() => { if (cur === c && !c.pc) cleanup('Пропущенный звонок'); }, RING_MS);
  }
  async function accept() {
    const c = cur; if (!c || c.role !== 'in' || c.pc) return;
    stopTone(); mode('live'); status('Соединяем…');
    try {
      c.local = await media(c.video);
      if (cur !== c) return c.local.getTracks().forEach(t => t.stop());
      c.$('.call-local').srcObject = c.local;
      c.ice = await ice();
      const pc = peer(c);
      await pc.setRemoteDescription(c.offer);
      await addIce(c, c.iceIn.splice(0));
      await pc.setLocalDescription(await pc.createAnswer());
      const r = await post(`/v3/call/${c.id}/signal`, { kind: 'answer', answer: { type: 'answer', sdp: pc.localDescription.sdp }, tab: TAB });
      if (!r.ok || r.ended) { cleanup(r.error || 'Звонок уже завершён'); return; }
      flushIce(c);
    } catch (e) { say(e.message || 'Не удалось ответить', true); hangup('hangup'); }
  }

  // ------------------------------------------------------------------ управление
  function toggleMic() {
    const c = cur; if (!c || !c.local) return;
    const t = c.local.getAudioTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; c.$('[data-c=mic]').classList.toggle('off', !t.enabled);
    post(`/v3/call/${c.id}/signal`, { kind: 'media', mic: t.enabled, cam: camOn(c) });
  }
  const camOn = c => { const v = c.local && c.local.getVideoTracks()[0]; return !!(v && v.enabled); };
  function toggleCam() {
    const c = cur; if (!c || !c.local) return;
    const t = c.local.getVideoTracks()[0]; if (!t) return say('Камера недоступна');
    t.enabled = !t.enabled; c.$('[data-c=cam]').classList.toggle('off', !t.enabled); c.el.classList.toggle('cam-off', !t.enabled);
    const a = c.local.getAudioTracks()[0];
    post(`/v3/call/${c.id}/signal`, { kind: 'media', cam: t.enabled, mic: !!(a && a.enabled) });
  }
  async function flip() {
    const c = cur; if (!c || !c.pc || !c.local) return;
    const old = c.local.getVideoTracks()[0]; if (!old) return;
    const face = c.face === 'environment' ? 'user' : 'environment';
    old.stop(); // на многих телефонах две камеры сразу не открыть
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { exact: face } } }).catch(() => navigator.mediaDevices.getUserMedia({ video: { facingMode: face } }));
      const nt = s.getVideoTracks()[0]; nt.enabled = old.enabled;
      const snd = c.pc.getSenders().find(x => x.track && x.track.kind === 'video');
      if (snd) await snd.replaceTrack(nt);
      c.local.removeTrack(old); c.local.addTrack(nt); c.face = face;
      c.$('.call-local').srcObject = c.local; c.el.classList.toggle('back-cam', face === 'environment');
    } catch (e) { say('Не удалось переключить камеру', true); }
  }
  function hangup(kind, msg) {
    const c = cur; if (!c) return;
    if (c.id) {
      const url = `/v3/call/${c.id}/signal`, body = JSON.stringify({ kind: kind === 'decline' ? 'decline' : 'hangup', tab: TAB });
      fetch(url, { method: 'POST', headers: HDR, credentials: 'same-origin', body, keepalive: true }).catch(() => {});
    }
    cleanup(msg || (c.t0 ? 'Звонок завершён' : ''));
  }
  function cleanup(msg) {
    const c = cur; if (!c) return;
    cur = null; stopTone();
    [c.clock, c.ping].forEach(clearInterval); [c.ringTo, c.lost, c.iceT].forEach(clearTimeout);
    try { c.pc && c.pc.close(); } catch (e) {}
    if (c.local) c.local.getTracks().forEach(t => t.stop());
    try { c.lock && c.lock.release(); } catch (e) {}
    awake(false);
    if (c.el) { c.el.classList.add('closing'); setTimeout(() => c.el.remove(), 250); }
    document.documentElement.classList.remove('in-call');
    if (msg) say(msg);
  }

  // ------------------------------------------------------------------ сигналы от сервера
  async function onEvent(e) {
    const c = cur, mine = c && c.id === e.call;
    if (e.kind === 'ring') return incoming(e);
    if (!mine) return;
    if (e.kind === 'answer' && c.role === 'out' && c.pc && !c.answered) {
      c.answered = true; clearTimeout(c.ringTo); stopTone(); status('Соединяем…');
      try { await c.pc.setRemoteDescription(e.answer); await addIce(c, c.iceIn.splice(0)); } catch (err) { hangup('hangup', 'Не удалось соединиться'); }
    } else if (e.kind === 'ice') {
      if (c.pc && c.pc.remoteDescription) addIce(c, e.candidates || []); else c.iceIn.push(...(e.candidates || []));
    } else if (e.kind === 'taken' && c.role === 'in' && e.tab !== TAB && !c.pc) {
      cleanup('Вы ответили на другом устройстве');
    } else if (e.kind === 'media') {
      c.el.classList.toggle('peer-cam-off', e.cam === false); c.el.classList.toggle('peer-mic-off', e.mic === false);
    } else if (e.kind === 'end') {
      const out = c.role === 'out';
      cleanup(e.status === 'declined' ? (out ? 'Собеседник отклонил звонок' : '') : e.status === 'missed' ? (out ? 'Не отвечает' : 'Пропущенный звонок') : 'Звонок завершён');
    }
  }
  async function loop() {
    let fails = 0;
    for (;;) {
      try {
        const r = await fetch(`/v3/call/poll?since=${since}`, { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin', cache: 'no-store' });
        if (r.status === 401 || r.status === 404) return;
        const j = await r.json();
        if (j.ice) ICE = j.ice;
        since = j.last;
        for (const e of j.events || []) await onEvent(e);
        fails = 0;
      } catch (e) { fails++; await sleep(Math.min(30000, 2000 * fails)); }
    }
  }

  // ------------------------------------------------------------------ кнопки и запуск
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-call]'); if (!b) return;
    e.preventDefault();
    start(b.dataset.call, b.dataset.video === '1', b.dataset.name, b.dataset.avatar);
  });
  window.addEventListener('pagehide', () => { if (cur && cur.id) hangup('hangup'); });
  window.addEventListener('beforeunload', e => { if (cur && cur.t0) { e.preventDefault(); e.returnValue = ''; } });
  window.nuvoraBack = () => { if (!cur) return false; say('Чтобы выйти, завершите звонок'); return true; }; // кнопка «назад» в Android-приложении
  window.nuvoraCall = { start, active: () => !!cur };
  setTimeout(loop, 1200);
})();
