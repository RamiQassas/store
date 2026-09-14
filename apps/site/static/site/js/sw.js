/* 
 * Raqamiyat Support Service Worker 
 * Handles background push notifications
 */

const STATIC_CACHE = 'raqamiyat-static-v20260914';
const STATIC_ASSETS = [
    '/static/site/img/app-icon.svg',
    '/static/site/manifest.webmanifest'
];

self.addEventListener('install', function(event) {
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(keys.map(function(key) {
                return caches.delete(key);
            }));
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function(event) {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

    // Network-first strategy for static files to ensure immediate updates
    event.respondWith(
        fetch(event.request).then(function(response) {
            return response;
        }).catch(function() {
            return caches.match(event.request);
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
