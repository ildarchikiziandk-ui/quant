self.addEventListener('push', function(event) {
    let data = {};
    try { data = event.data.json(); } catch(e) {}
    const title = data.title || 'Quant';
    const options = {
        body: data.body || '',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        data: { url: data.url || '/' },
        vibrate: [200, 100, 200]
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const url = event.notification.data.url || '/';
    event.waitUntil(clients.openWindow(url));
});

self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => clients.claim());