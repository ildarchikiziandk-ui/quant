const CACHE_NAME = 'app-__VERSION__';
const BRAND = '__BRAND__';
const PRECACHE = ['/static/icon-192.png', '/static/css/app.css', '/static/js/app.js', '/offline'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(PRECACHE)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    // статика: сначала кэш, потом сеть
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      const copy = res.clone(); caches.open(CACHE_NAME).then(c => c.put(req, copy)); return res;
    })));
    return;
  }
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/offline')));
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
    for (const c of cs) { if (new URL(c.url).pathname === url && 'focus' in c) return c.focus(); }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});
