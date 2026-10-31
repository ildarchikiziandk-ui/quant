const CACHE_NAME = 'app-__VERSION__';
const OLD_MEDIA = 'media-v1';  // раньше хранили и фото; теперь без интернета сохраняется только текст — кэш фото стираем
const PAGES_CACHE = 'pages-v1';  // последние открытые страницы — их видно без интернета
const PAGES_MAX = 120;
const SLOW_MS = 3500;  // сеть тормозит дольше — сразу показываем сохранённую страницу, а свежую подкладываем в кэш
// какие страницы сохраняем для офлайна (личные, но только на этом устройстве; стираются при выходе из аккаунта)
const PAGE_OK = /^\/($|messages\/?$|notifications$|explore$|games(\/2048|\/word|\/offline)?$|help$|ai$|capsule$|bookmarks$|whats-new$|profile\/[\w.-]+$|post\/\d+$|messages\/[\w.-]+$)/;
const BRAND = '__BRAND__';
const PRECACHE = ['/static/icon-192.png', '/static/brand/logo-180.png', '/offline'];
// «Игры без интернета»: страница, её скрипты, стили, иконки и шрифты скачиваются сразу (список подставляет сервер)
const OFFLINE = [/*__OFFLINE__*/];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(PRECACHE).catch(() => {})
    .then(() => Promise.all(OFFLINE.map(u => c.add(u).catch(() => {}))))));  // одна неудача не мешает остальным
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  caches.delete(OLD_MEDIA);
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME && k !== PAGES_CACHE).map(k => caches.delete(k)))));
  if (self.registration.navigationPreload) e.waitUntil(self.registration.navigationPreload.enable().catch(() => {}));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.headers.has('range') || url.pathname.startsWith('/static/promo/') || url.pathname.startsWith('/download/')) return;  // видео и скачивания — напрямую
  if (url.pathname.startsWith('/static/') || (url.pathname.startsWith('/i18n/') && url.search)) {
    // статика (и переведённые скрипты с ?v=): сначала кэш, потом сеть
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      if (res.status === 200) { const copy = res.clone(); caches.open(CACHE_NAME).then(c => c.put(req, copy)); } return res;
    })));
    return;
  }
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      const key = url.pathname + url.search;
      const c = await caches.open(PAGES_CACHE);
      const saved = PAGE_OK.test(url.pathname) ? await c.match(key) : null;
      const net = (async () => {
        const res = (await e.preloadResponse) || await fetch(req);
        if (res.ok && !res.redirected && res.type === 'basic' && PAGE_OK.test(url.pathname)) await savePage(c, key, res.clone());
        return res;
      })();
      try {
        if (!saved) return await net;
        // есть сохранённая копия: ждём сеть не дольше SLOW_MS, иначе показываем копию (свежая догрузится в кэш)
        const slow = new Promise(r => setTimeout(() => r(null), SLOW_MS));
        const res = await Promise.race([net, slow]);
        if (res) return res;
        e.waitUntil(net.catch(() => {}));
        return markSaved(saved);
      } catch (err) {
        const games = url.pathname === '/games/offline' && await caches.match('/games/offline', { cacheName: CACHE_NAME });  // свежая, под текущую статику
        const page = games || saved || (await c.match(url.pathname));
        return page ? markSaved(page) : ((await caches.match('/offline')) || Response.error());
      }
    })());
  }
});

// Сохраняем только HTML страницы (без фото и видео — они грузятся по сети), последние PAGES_MAX штук
async function savePage(c, key, res) {
  try {
    await c.put(key, res);
    const k = await c.keys();
    if (k.length > PAGES_MAX) await Promise.all(k.slice(0, k.length - PAGES_MAX).map(x => c.delete(x)));
  } catch (err) { /* нет места — не страшно */ }
}

// Помечаем сохранённую копию, чтобы страница показала плашку «Без интернета — сохранённая версия»
async function markSaved(res) {
  const html = await res.text();
  return new Response(html.replace('<html ', '<html data-saved-copy="1" '), { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

// Страница чатов просит заранее сохранить последние переписки — тогда их видно без интернета
self.addEventListener('message', e => {
  const d = e.data || {};
  if (d.type !== 'cache-pages' || !Array.isArray(d.urls)) return;
  e.waitUntil(caches.open(PAGES_CACHE).then(c => Promise.all(d.urls.slice(0, 12).map(async u => {
    const url = new URL(u, location.origin);
    if (url.origin !== location.origin || !PAGE_OK.test(url.pathname)) return;
    try {
      const res = await fetch(url.pathname, { credentials: 'same-origin' });
      if (res.ok && !res.redirected) await savePage(c, url.pathname, res);
    } catch (err) { /* нет сети */ }
  }))));
});

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data.json(); } catch (err) { data = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(data.title || BRAND, {
    body: data.body || '', icon: '/static/icon-192.png', badge: '/static/icon-192.png',
    data: { url: data.url || '/' }, vibrate: [200, 100, 200], tag: data.url || 'app-notification', renotify: true
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
    const want = new URL(url, self.location.origin);
    for (const c of cs) { const u = new URL(c.url); if (u.pathname === want.pathname && 'focus' in c) return c.navigate && want.href !== c.url ? c.navigate(want.href).then(w => w && w.focus()) : c.focus(); }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});
