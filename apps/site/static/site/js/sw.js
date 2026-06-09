/* 
 * Raqamiyat Support Service Worker 
 * Handles background push notifications
 */

const STATIC_CACHE = 'raqamiyat-static-v1';
const STATIC_ASSETS = [
    '/static/site/css/app.css',
    '/static/site/js/app.js',
    '/static/site/js/push.js',
    '/static/site/img/app-icon.svg',
    '/static/site/manifest.webmanifest'
];

self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(STATIC_CACHE).then(function(cache) {
            return cache.addAll(STATIC_ASSETS).catch(function() {
                return Promise.resolve();
            });
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(keys.filter(function(key) {
                return key !== STATIC_CACHE && key.indexOf('raqamiyat-') === 0;
            }).map(function(key) {
                return caches.delete(key);
            }));
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function(event) {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;

    event.respondWith(
        caches.match(event.request).then(function(cached) {
            return cached || fetch(event.request).then(function(response) {
                const copy = response.clone();
                caches.open(STATIC_CACHE).then(function(cache) {
                    cache.put(event.request, copy);
                });
                return response;
            });
        })
    );
});

self.addEventListener('push', function(event) {
    if (!event.data) return;
    
    try {
        const payload = event.data.json();
        const title = payload.title || 'Raqamiyat | رقميات';
        const options = {
            body: payload.body || '',
            icon: payload.icon || null,
            badge: payload.badge || null,
            image: payload.image || null,
            data: {
                url: payload.action_url || '/dashboard/'
            },
            vibrate: [100, 50, 100],
            actions: payload.actions || []
        };

        event.waitUntil(
            self.registration.showNotification(title, options)
        );
    } catch (e) {
        console.error('Push Event Error:', e);
    }
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    
    const targetUrl = event.notification.data.url;
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url === targetUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
