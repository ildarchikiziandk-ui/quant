const CACHE_NAME = 'quant-v3';

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache =>
            cache.addAll(['/static/icon-192.png', '/offline'])
        )
    );
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    clients.claim();
});

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request).catch(() =>
            caches.match(e.request).then(r => r || caches.match('/offline'))
        )
    );
});

self.addEventListener('push', e => {
    let data = {};
    try { data = e.data.json(); } catch(err) {}
    e.waitUntil(
        self.registration.showNotification(data.title || 'Quant', {
            body: data.body || '',
            icon: '/static/icon-192.png',
            badge: '/static/icon-192.png',
            data: { url: data.url || '/' },
            vibrate: [200, 100, 200],
            tag: 'quant-notification',
            renotify: true
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({type:'window'}).then(cs => {
            const url = e.notification.data.url || '/';
            for (const c of cs) {
                if (c.url === url && 'focus' in c) return c.focus();
            }
            if (clients.openWindow) return clients.openWindow(url);
        })
    );
});