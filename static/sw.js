const CACHE_NAME = 'app-__VERSION__';
const MEDIA_CACHE = 'media-v1';  // фото и видео из ленты: имена файлов уникальные, их можно хранить
const MEDIA_MAX = 400;
const PAGES_CACHE = 'pages-v1';  // последние открытые страницы — их видно без интернета
const PAGES_MAX = 40;
// какие страницы сохраняем для офлайна (личные, но только на этом устройстве; стираются при выходе из аккаунта)
const PAGE_OK = /^\/($|messages\/?$|notifications$|explore$|games(\/2048|\/word)?$|help$|ai$|capsule$|bookmarks$|whats-new$|profile\/[\w.-]+$|post\/\d+$|messages\/[\w.-]+$)/;
const BRAND = '__BRAND__';
const PRECACHE = ['/static/icon-192.png', '/static/brand/logo-180.png', '/offline'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(PRECACHE)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME && k !== MEDIA_CACHE && k !== PAGES_CACHE).map(k => caches.delete(k)))));
  if (self.registration.navigationPreload) e.waitUntil(self.registration.navigationPreload.enable().catch(() => {}));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.headers.has('range') || url.pathname.startsWith('/static/promo/') || url.pathname.startsWith('/download/')) return;  // видео и скачивания — напрямую
  if (url.pathname.startsWith('/static/')) {
    // статика: сначала кэш, потом сеть
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      if (res.status === 200) { const copy = res.clone(); caches.open(CACHE_NAME).then(c => c.put(req, copy)); } return res;
    })));
    return;
  }
  if (url.pathname.startsWith('/uploads/') && req.destination === 'image') {
    e.respondWith(caches.open(MEDIA_CACHE).then(c => c.match(req).then(r => r || fetch(req).then(res => {
      if (res.ok) { c.put(req, res.clone()); c.keys().then(k => { if (k.length > MEDIA_MAX) k.slice(0, k.length - MEDIA_MAX).forEach(x => c.delete(x)); }); }
      return res;
    }))));
    return;
  }
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const res = (await e.preloadResponse) || await fetch(req);
        if (res.ok && !res.redirected && res.type === 'basic' && PAGE_OK.test(url.pathname)) {
          const copy = res.clone();
          caches.open(PAGES_CACHE).then(c => c.put(url.pathname + url.search, copy).then(() => c.keys()).then(k => {
            if (k.length > PAGES_MAX) k.slice(0, k.length - PAGES_MAX).forEach(x => c.delete(x));
          })).catch(() => {});
        }
        return res;
      } catch (err) {
        const c = await caches.open(PAGES_CACHE);
        return (await c.match(url.pathname + url.search)) || (await c.match(url.pathname)) || (await caches.match('/offline')) || Response.error();
      }
    })());
  }
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
