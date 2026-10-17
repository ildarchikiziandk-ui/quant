/* Секретные чаты Nuvora: сквозное шифрование по ГОСТ прямо в браузере.
 *
 * Ключи:     ГОСТ Р 34.10-2012, 256 бит (кривая id-tc26-gost-3410-2012-256-paramSetA), своя пара на каждый чат.
 *            Закрытый ключ хранится только на этом устройстве (localStorage) и никогда не отправляется на сервер.
 * Общий ключ: VKO ГОСТ Р 34.10-2012 (ukm — 8 случайных байт от сервера) → HMAC_GOSTR3411_2012_256 (Р 50.1.113-2016)
 *            даёт два независимых ключа: для шифрования и для имитовставки.
 * Сообщение: «Кузнечик» (ГОСТ Р 34.12-2015) в режиме гаммирования CTR (ГОСТ Р 34.13-2015) со случайным IV,
 *            затем имитовставка MAC-128 (ГОСТ Р 34.13-2015) над заголовком, IV и шифротекстом (encrypt-then-MAC).
 *            Заголовок связывает сообщение с чатом и отправителем, поэтому его нельзя переслать в другой чат или
 *            выдать за сообщение собеседника.
 */
(function (global) {
  'use strict';
  var E = global.GostEngine;
  var DH = { name: 'GOST R 34.10', version: 2012, mode: 'DH', namedCurve: 'X-256-A', length: 256 };
  var VERSION = 'nv1';

  function hex(buf) {
    var b = new Uint8Array(buf), s = '';
    for (var i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16);
    return s;
  }
  function unhex(h) {
    var b = new Uint8Array(h.length / 2);
    for (var i = 0; i < b.length; i++) b[i] = parseInt(h.substr(i * 2, 2), 16);
    return b.buffer;
  }
  function utf8(s) { return new TextEncoder().encode(s).buffer; }
  function concat() {
    var n = 0, i, parts = Array.prototype.map.call(arguments, function (x) { return new Uint8Array(x); });
    for (i = 0; i < parts.length; i++) n += parts[i].length;
    var out = new Uint8Array(n), o = 0;
    for (i = 0; i < parts.length; i++) { out.set(parts[i], o); o += parts[i].length; }
    return out.buffer;
  }
  function b64(buf) {
    var b = new Uint8Array(buf), s = '';
    for (var i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function unb64(s) {
    var bin = atob(s), b = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    return b.buffer;
  }
  function random(n) { var b = new Uint8Array(n); global.crypto.getRandomValues(b); return b.buffer; }
  function hmac() { return E.getGostDigest({ name: 'GOST R 34.11', version: 2012, length: 256, mode: 'HMAC' }); }
  function cipher(iv) { return E.getGostCipher({ name: 'GOST R 34.12', version: 2015, length: 128, mode: 'ES', block: 'CTR', iv: iv }); }
  function mac() { return E.getGostCipher({ name: 'GOST R 34.12', version: 2015, length: 128, mode: 'MAC', macLength: 128 }); }
  function header(chatId, senderId) { return utf8(VERSION + '|' + chatId + '|' + senderId + '|'); }

  var Core = {
    generateKeys: function () {
      var k = E.getGostSign(DH).generateKey();
      return { priv: hex(k.privateKey), pub: hex(k.publicKey) };
    },
    derive: function (privHex, peerPubHex, ukmHex) {
      var alg = Object.assign({}, DH, { 'public': unhex(peerPubHex), ukm: unhex(ukmHex) });
      var shared = E.getGostSign(alg).deriveBits(unhex(privHex), 256);
      var h = hmac();
      return { enc: h.sign(shared, utf8('nuvora-secret-enc-v1')), mac: h.sign(shared, utf8('nuvora-secret-mac-v1')) };
    },
    seal: function (keys, chatId, senderId, text) {
      var iv = random(8);
      var body = utf8(JSON.stringify({ t: String(text), ts: Date.now() }));
      var ct = cipher(iv).encrypt(keys.enc, body);
      var tag = mac().sign(keys.mac, concat(header(chatId, senderId), iv, ct));
      return b64(concat(iv, tag, ct));
    },
    open: function (keys, chatId, senderId, payload) {
      var raw = new Uint8Array(unb64(payload));
      if (raw.length < 25) throw new Error('short');
      var iv = raw.slice(0, 8).buffer, tag = raw.slice(8, 24).buffer, ct = raw.slice(24).buffer;
      if (!mac().verify(keys.mac, tag, concat(header(chatId, senderId), iv, ct))) throw new Error('mac');
      return JSON.parse(new TextDecoder().decode(cipher(iv).decrypt(keys.enc, ct)));
    },
    fingerprint: function (aPub, bPub, ukm) {
      var d = E.getGostDigest({ name: 'GOST R 34.11', version: 2012, length: 256 }).digest(concat(unhex(aPub), unhex(bPub), unhex(ukm)));
      return hex(d).slice(0, 32).toUpperCase().match(/.{4}/g).join(' ');
    }
  };
  global.NuvoraSecret = Core;

  if (typeof document === 'undefined') return;

  // ---------------------------------------------------------------- интерфейс
  var J = { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch', 'Accept': 'application/json' };
  function post(url, data) {
    return fetch(url, { method: 'POST', headers: J, credentials: 'same-origin', body: JSON.stringify(data || {}) })
      .then(function (r) { return r.json(); });
  }
  function get(url) { return fetch(url, { headers: J, credentials: 'same-origin' }).then(function (r) { return r.json(); }); }
  function store(me, chatId) { return 'nv_sc_' + me + '_' + chatId; }
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } }
  function lsDel(k) { try { localStorage.removeItem(k); } catch (e) { /* ничего */ } }
  function el(tag, cls, text) { var x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }

  // Начать новый чат
  var startForm = document.getElementById('secret-start');
  if (startForm) {
    startForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var btn = startForm.querySelector('button'), err = document.getElementById('secret-start-error');
      var me = startForm.getAttribute('data-me');
      btn.disabled = true; btn.textContent = 'Создаём ключи…'; err.textContent = '';
      setTimeout(function () {
        var keys = Core.generateKeys();
        post('/secret/start', { username: startForm.username.value, ttl: startForm.ttl.value, pub: keys.pub }).then(function (r) {
          if (!r.ok) throw new Error(r.error || 'Ошибка');
          if (!lsSet(store(me, r.id), keys.priv)) throw new Error('Браузер не даёт сохранить ключ (приватный режим?)');
          location.href = '/secret/' + r.id;
        }).catch(function (e) { err.textContent = e.message; btn.disabled = false; btn.textContent = 'Начать секретный чат'; });
      }, 20);
    });
  }

  var root = document.getElementById('secret-chat');
  if (!root) return;
  var chatId = root.getAttribute('data-chat'), me = +root.getAttribute('data-me');
  var box = document.getElementById('secret-messages'), form = document.getElementById('secret-send');
  var statusEl = document.getElementById('secret-status'), fpEl = document.getElementById('secret-fp');
  var keys = null, last = 0, state = null, shown = {}, timer = null;

  function setStatus(t, bad) { statusEl.textContent = t; statusEl.className = 'small ' + (bad ? 'error-text' : 'muted'); }

  function addMessage(m) {
    if (shown[m.id]) return;
    var mine = m.sender === me, node = el('div', 'secret-msg ' + (mine ? 'mine' : 'theirs'));
    node.setAttribute('data-id', m.id);
    try {
      var data = Core.open(keys, chatId, m.sender, m.payload);
      node.appendChild(el('div', 'secret-text', data.t));
    } catch (e) {
      node.appendChild(el('div', 'secret-text error-text', 'Не удалось проверить подлинность сообщения — оно отброшено'));
    }
    var meta = new Date(m.at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    if (m.expires) meta += ' · исчезнет в ' + new Date(m.expires).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    node.appendChild(el('div', 'tiny faint', meta));
    shown[m.id] = node;
    box.appendChild(node);
    box.scrollTop = box.scrollHeight;
  }

  function poll() {
    get('/secret/' + chatId + '/messages?after=' + last).then(function (r) {
      if (!r.ok) { setStatus(r.error || 'Чат недоступен', true); clearInterval(timer); return; }
      r.messages.forEach(function (m) { addMessage(m); last = Math.max(last, m.id); });
      var alive = {};
      r.alive.forEach(function (id) { alive[id] = 1; });
      Object.keys(shown).forEach(function (id) { if (!alive[id]) { shown[id].remove(); delete shown[id]; } });
      var empty = document.getElementById('secret-empty');
      if (empty) empty.style.display = Object.keys(shown).length ? 'none' : '';
    }).catch(function () { /* сеть пропала — попробуем в следующий раз */ });
  }

  function activate() {
    var priv = lsGet(store(me, chatId));
    var mineA = state.a_id === me, peerPub = mineA ? state.b_pub : state.a_pub;
    try { keys = Core.derive(priv, peerPub, state.ukm); } catch (e) { setStatus('Ошибка ключей: ' + e.message, true); return; }
    fpEl.textContent = Core.fingerprint(state.a_pub, state.b_pub, state.ukm);
    document.getElementById('secret-fp-box').style.display = '';
    form.style.display = '';
    setStatus('Сквозное шифрование ГОСТ включено. Сервер не может прочитать переписку.');
    poll();
    timer = setInterval(poll, 2500);
  }

  function boot() {
    get('/secret/' + chatId + '/state').then(function (s) {
      if (!s.ok) { setStatus(s.error || 'Чат не найден', true); return; }
      state = s;
      var priv = lsGet(store(me, chatId));
      // приглашение ещё не принято на сервере (в том числе если прошлый раз «Принять» не дошёл) — создаём ключи заново
      if (s.status === 'pending' && s.b_id === me && !s.b_pub) {
        setStatus('Создаём ключи шифрования…');
        setTimeout(function () {
          var k = Core.generateKeys();
          if (!lsSet(store(me, chatId), k.priv)) { setStatus('Браузер не даёт сохранить ключ (приватный режим?)', true); return; }
          post('/secret/' + chatId + '/accept', { pub: k.pub }).then(function (r) {
            if (!r.ok) { setStatus(r.error, true); return; }
            boot();
          }).catch(function () { setStatus('Нет связи с сервером. Обновите страницу, чтобы попробовать ещё раз.', true); });
        }, 20);
        return;
      }
      if (!priv) {
        setStatus('Ключ этого чата хранится на другом устройстве или был удалён. Секретные чаты открываются только там, где были созданы.', true);
        return;
      }
      if (s.status === 'pending') {
        setStatus('Ждём, пока собеседник откроет приглашение…');
        setTimeout(boot, 3000);
        return;
      }
      activate();
    });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var text = form.text.value.trim();
    if (!text || !keys) return;
    var payload = Core.seal(keys, chatId, me, text);
    form.text.value = '';
    post('/secret/' + chatId + '/send', { payload: payload }).then(function (r) {
      if (!r.ok) { setStatus(r.error, true); form.text.value = text; return; }
      poll();
    });
  });
  form.text.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });

  var ttlSel = document.getElementById('secret-ttl');
  if (ttlSel) ttlSel.addEventListener('change', function () {
    post('/secret/' + chatId + '/ttl', { ttl: ttlSel.value }).then(function (r) {
      setStatus(r.ok ? 'Таймер самоуничтожения изменён — действует для новых сообщений' : r.error, !r.ok);
    });
  });
  var del = document.getElementById('secret-delete');
  if (del) del.addEventListener('click', function () {
    if (!confirm('Удалить секретный чат у обоих участников? Сообщения и ключи будут уничтожены.')) return;
    post('/secret/' + chatId + '/delete').then(function () { lsDel(store(me, chatId)); location.href = '/secret'; });
  });

  boot();
})(typeof self !== 'undefined' ? self : globalThis);
