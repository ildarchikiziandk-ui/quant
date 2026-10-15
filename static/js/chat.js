/* Чаты: запись голосовых и кружков одной кнопкой (как в Telegram) и плееры сообщений.
 *
 * Кнопка записи: по умолчанию — голосовое. Короткое нажатие переключает режим «голосовое ↔ кружок».
 * Долгое нажатие начинает запись; отпускать можно — запись идёт дальше. Отправка — кнопкой «Отправить»,
 * отмена — корзиной.
 */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const LONG_PRESS = 280, MAX_VOICE = 300, MAX_CIRCLE = 60;
  const fmt = s => { if (!isFinite(s)) s = 0; s = Math.max(0, Math.round(s || 0)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };

  // ------------------------------------------------------------------ плееры
  let current = null;  // играет только одно сообщение
  function stopOthers(el) { if (current && current !== el) { current.pause(); } current = el; }

  function hashBars(src, n) {  // запасной «рисунок» волны, если файл не удалось разобрать
    let h = 0; for (let i = 0; i < src.length; i++) h = (h * 31 + src.charCodeAt(i)) >>> 0;
    const out = []; for (let i = 0; i < n; i++) { h = (h * 1103515245 + 12345) >>> 0; out.push(.25 + (h % 1000) / 1333); }
    return out;
  }
  const peaksCache = {};
  async function peaks(src, n) {
    if (peaksCache[src]) return peaksCache[src];
    try {
      const buf = await (await fetch(src)).arrayBuffer();
      const AC = window.AudioContext || window.webkitAudioContext;
      const ctx = new AC(); const audio = await ctx.decodeAudioData(buf); ctx.close?.();
      const data = audio.getChannelData(0), step = Math.floor(data.length / n), out = [];
      let max = 0;
      for (let i = 0; i < n; i++) { let m = 0; for (let j = i * step; j < (i + 1) * step; j += 16) m = Math.max(m, Math.abs(data[j] || 0)); out.push(m); max = Math.max(max, m); }
      return (peaksCache[src] = out.map(v => .15 + .85 * (max ? v / max : 0)));
    } catch (e) { return (peaksCache[src] = hashBars(src, n)); }
  }
  function drawBars(wave, values) {
    wave.innerHTML = values.map(v => `<i style="height:${Math.round(v * 100)}%"></i>`).join('');
  }
  // У записей MediaRecorder (webm) нет длительности в заголовке — узнаём её, перемотав в конец
  function fixDuration(media, done) {
    const ready = () => isFinite(media.duration) && media.duration > 0;
    const go = () => {
      if (ready()) { done(); return; }
      const t = () => { media.removeEventListener('timeupdate', t); media.currentTime = 0; done(); };
      media.addEventListener('timeupdate', t);
      try { media.currentTime = 1e101; } catch (e) { done(); }
    };
    if (media.readyState >= 1) go(); else media.addEventListener('loadedmetadata', go, { once: true });
  }
  function setupVoice(el) {
    if (el.dataset.ready) return; el.dataset.ready = '1';
    const audio = $('audio', el), play = $('.vplay', el), wave = $('.vwave', el), dur = $('.vdur', el), speed = $('.vspeed', el);
    const N = 36; drawBars(wave, hashBars(el.dataset.src, N));
    const io = new IntersectionObserver(es => { if (es[0].isIntersecting) { io.disconnect(); peaks(el.dataset.src, N).then(v => { drawBars(wave, v); paint(); }); } });
    io.observe(el);
    const paint = () => {
      const p = audio.duration ? audio.currentTime / audio.duration : 0, bars = wave.children, k = Math.round(p * bars.length);
      for (let i = 0; i < bars.length; i++) bars[i].classList.toggle('on', i < k);
      dur.textContent = fmt(audio.paused && !audio.currentTime ? audio.duration : audio.currentTime);
      if (!isFinite(audio.duration)) return;
    };
    fixDuration(audio, () => { dur.textContent = fmt(audio.duration); });
    audio.addEventListener('timeupdate', paint);
    audio.addEventListener('play', () => { stopOthers(audio); el.classList.add('playing'); play.innerHTML = ICON('pause', 'i'); });
    audio.addEventListener('pause', () => { el.classList.remove('playing'); play.innerHTML = ICON('play', 'i'); });
    audio.addEventListener('ended', () => { audio.currentTime = 0; paint(); });
    play.onclick = () => audio.paused ? audio.play() : audio.pause();
    wave.onclick = e => { if (!audio.duration) return; const r = wave.getBoundingClientRect(); audio.currentTime = audio.duration * (e.clientX - r.left) / r.width; if (audio.paused) audio.play(); };
    const rates = [1, 1.5, 2];
    speed.onclick = () => { const i = (rates.indexOf(audio.playbackRate) + 1) % rates.length; audio.playbackRate = rates[i]; speed.textContent = rates[i] + '×'; };
  }
  function setupCircle(el) {
    if (el.dataset.ready) return; el.dataset.ready = '1';
    const v = $('video', el), ring = $('.vring circle', el), dur = $('.vdur', el);
    const L = 2 * Math.PI * 48; ring.style.strokeDasharray = L; ring.style.strokeDashoffset = L;
    fixDuration(v, () => { dur.textContent = fmt(v.duration); });
    v.addEventListener('timeupdate', () => {
      if (!v.muted && v.duration) { ring.style.strokeDashoffset = L * (1 - v.currentTime / v.duration); dur.textContent = fmt(v.duration - v.currentTime); }
    });
    v.addEventListener('ended', () => { reset(); });
    v.addEventListener('pause', () => { if (!v.muted) el.classList.add('paused'); });
    v.addEventListener('play', () => el.classList.remove('paused'));
    function reset() { v.muted = true; v.loop = true; el.classList.remove('sound', 'paused'); ring.style.strokeDashoffset = L; if (isFinite(v.duration)) dur.textContent = fmt(v.duration); v.play().catch(() => {}); }
    // в ленте кружок тихо проигрывается по кругу, нажатие — со звуком с начала, повторное — пауза
    const io = new IntersectionObserver(es => { es.forEach(e => { if (e.isIntersecting) { if (v.muted) v.play().catch(() => {}); } else if (v.muted) v.pause(); }); }, { threshold: .4 });
    io.observe(el);
    el.addEventListener('click', () => {
      if (v.muted) { stopOthers(v); v.muted = false; v.loop = false; v.currentTime = 0; el.classList.add('sound'); v.play(); }
      else if (v.paused) v.play(); else v.pause();
    });
    v._reset = reset;
  }
  function enhance(root) {
    (root || document).querySelectorAll?.('.vmsg').forEach(setupVoice);
    (root || document).querySelectorAll?.('.vcircle').forEach(setupCircle);
  }
  window.addEventListener('DOMContentLoaded', () => enhance(document));
  new MutationObserver(list => list.forEach(r => r.addedNodes.forEach(n => { if (n.nodeType === 1) enhance(n); }))).observe(document.documentElement, { childList: true, subtree: true });
  // когда другое сообщение начинает играть, кружок со звуком возвращается в тихий режим
  document.addEventListener('play', e => { const t = e.target; if (t.muted) return; if (current && current !== t && current._reset && !current.muted) current._reset(); }, true);

  // ------------------------------------------------------------------ запись
  /**
   * App.chatComposer({ input, onText(text), onMedia(blob, kind, filename) })
   * Разметка: .cmp (контейнер), внутри .cmp-rec, .cmp-send, .rec-panel, .rec-circle.
   */
  window.chatComposer = function (opts) {
    const root = opts.root, input = opts.input;
    const recBtn = $('.cmp-rec', root), sendBtn = $('.cmp-send', root), panel = $('.rec-panel', root);
    const circleBox = $('.rec-circle', root), preview = $('video', circleBox), timeEl = $('.rec-time', panel), label = $('.rec-label', panel);
    const meter = $('.rec-meter', panel);
    let mode = 'audio', rec = null, stream = null, chunks = [], t0 = 0, timer = null, pressTimer = null, cancelled = false, audioCtx = null, raf = 0;

    function refresh() {
      const recording = rec && rec.state === 'recording';
      const hasText = input.value.trim().length > 0;
      root.classList.toggle('recording', !!recording);
      sendBtn.classList.toggle('hidden', !(hasText || recording));
      recBtn.classList.toggle('hidden', hasText || !!recording);
      recBtn.innerHTML = ICON(mode === 'audio' ? 'mic' : 'video-circle', 'i');
      recBtn.title = mode === 'audio' ? 'Голосовое: удерживайте, чтобы записать. Нажмите — переключить на кружок' : 'Кружок: удерживайте, чтобы записать. Нажмите — переключить на голосовое';
    }
    input.addEventListener('input', refresh);
    refresh();

    function hint(text) {
      let h = $('.rec-hint', root);
      if (!h) { h = document.createElement('div'); h.className = 'rec-hint'; root.appendChild(h); }
      h.textContent = text; h.classList.add('show'); clearTimeout(h._t); h._t = setTimeout(() => h.classList.remove('show'), 1600);
    }
    recBtn.addEventListener('pointerdown', e => {
      if (e.button) return; e.preventDefault();
      pressTimer = setTimeout(() => { pressTimer = null; start(); }, LONG_PRESS);
    });
    const release = () => {
      if (pressTimer) {  // короткое нажатие — переключить режим
        clearTimeout(pressTimer); pressTimer = null;
        mode = mode === 'audio' ? 'video' : 'audio'; refresh();
        hint(mode === 'audio' ? 'Голосовое сообщение — удерживайте для записи' : 'Видеокружок — удерживайте для записи');
        navigator.vibrate?.(10);
      }
    };
    recBtn.addEventListener('pointerup', release);
    recBtn.addEventListener('pointerleave', () => { if (pressTimer) { clearTimeout(pressTimer); pressTimer = null; } });
    recBtn.addEventListener('contextmenu', e => e.preventDefault());
    recBtn.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); start(); } });

    async function start() {
      if (rec && rec.state === 'recording') return;
      const kind = mode;
      try {
        stream = await navigator.mediaDevices.getUserMedia(kind === 'video' ? { audio: true, video: { facingMode: 'user', width: 480, height: 480 } } : { audio: true });
      } catch (e) { App.toast('Нет доступа к ' + (kind === 'video' ? 'камере' : 'микрофону'), true); return; }
      const types = kind === 'video' ? ['video/webm;codecs=vp9,opus', 'video/webm', 'video/mp4'] : ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
      const mime = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
      chunks = []; cancelled = false;
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      rec.onstop = () => finish(kind, rec.mimeType || mime);
      rec.start(250); t0 = Date.now(); navigator.vibrate?.(20);
      label.textContent = kind === 'video' ? 'Видеокружок' : 'Голосовое';
      panel.classList.remove('hidden');
      if (kind === 'video') { preview.srcObject = stream; circleBox.classList.remove('hidden'); preview.play().catch(() => {}); }
      else startMeter();
      timer = setInterval(() => {
        const s = (Date.now() - t0) / 1000; timeEl.textContent = fmt(s);
        circleBox.style.setProperty('--p', Math.min(1, s / MAX_CIRCLE));
        if (s >= (kind === 'video' ? MAX_CIRCLE : MAX_VOICE)) stop(false);
      }, 200);
      refresh();
    }
    function startMeter() {
      try {
        const AC = window.AudioContext || window.webkitAudioContext; audioCtx = new AC();
        const an = audioCtx.createAnalyser(); an.fftSize = 256; audioCtx.createMediaStreamSource(stream).connect(an);
        const data = new Uint8Array(an.frequencyBinCount);
        const bars = Array.from({ length: 24 }, () => { const i = document.createElement('i'); meter.appendChild(i); return i; });
        const loop = () => { an.getByteFrequencyData(data); bars.forEach((b, k) => { b.style.height = Math.max(8, data[k * 2] / 2.55) + '%'; }); raf = requestAnimationFrame(loop); };
        loop();
      } catch (e) { /* без индикатора громкости */ }
    }
    function stop(cancel) { cancelled = !!cancel; if (rec && rec.state === 'recording') rec.stop(); }
    async function finish(kind, mime) {
      clearInterval(timer); cancelAnimationFrame(raf); audioCtx?.close?.(); audioCtx = null; meter.innerHTML = '';
      stream?.getTracks().forEach(t => t.stop()); preview.srcObject = null;
      panel.classList.add('hidden'); circleBox.classList.add('hidden'); timeEl.textContent = '0:00';
      const blob = new Blob(chunks, { type: (mime || '').split(';')[0] || (kind === 'video' ? 'video/webm' : 'audio/webm') });
      rec = null; refresh();
      if (cancelled || !blob.size || Date.now() - t0 < 700) { if (!cancelled) hint('Слишком коротко — удерживайте дольше'); return; }
      const ext = blob.type.includes('mp4') ? '.mp4' : blob.type.includes('ogg') ? '.ogg' : '.webm';
      await opts.onMedia(blob, kind, (kind === 'video' ? 'circle' : 'voice') + ext);
    }
    sendBtn.addEventListener('click', e => {
      e.preventDefault();
      if (rec && rec.state === 'recording') { stop(false); return; }
      const text = input.value.trim(); if (!text) return;
      opts.onText(text);
    });
    $('.rec-cancel', panel).addEventListener('click', () => stop(true));
    return { refresh, stop };
  };
})();
