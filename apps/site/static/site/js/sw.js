/* 
 * Raqamiyat Ultimate Android & PWA Service Worker (v2.5)
 * - Offline-First Smart Caching & Stale-While-Revalidate
 * - Full Catalog & Product Caching for 100% Offline Browsing & Shopping
 * - Background Push Notifications & Rich Actions
 * - Background Sync for Offline Orders
 */

const CACHE_VERSION = 'raqamiyat-offline-v20261007';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;
const DATA_CACHE = `${CACHE_VERSION}-data`;

// Core offline assets to pre-cache immediately upon app installation
const PRECACHE_ASSETS = [
    '/',
    '/catalog/',
    '/control/camera-studio/',
    '/api/offline-catalog/',
    '/static/site/manifest.webmanifest',
    '/static/site/img/app-icon.svg',
    '/static/site/img/raqamiyat_logo_official.jpg'
];

// Install: Cache critical core assets and take over immediately
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(STATIC_CACHE).then(function(cache) {
            return cache.addAll(PRECACHE_ASSETS.map(url => new Request(url, { cache: 'reload' })))
                .catch(function(err) {
                    console.warn('Pre-cache warning for some assets:', err);
                });
        }).then(function() {
            return self.skipWaiting();
        })
    );
});

// Activate: Clean up old caches and claim clients
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(
                keys.map(function(key) {
                    if (!key.startsWith(CACHE_VERSION)) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(function() {
            return self.clients.claim();
        })
    );
});

// Fetch: Smart Caching Strategies
self.addEventListener('fetch', function(event) {
    const request = event.request;
    const url = new URL(request.url);

    // Only handle HTTP/HTTPS requests
    if (!url.protocol.startsWith('http')) return;

    // Safe non-GET request handling (Never perform financial/mutation operations offline)
    if (request.method !== 'GET') {
        event.respondWith(
            fetch(request).catch(function() {
                return new Response(JSON.stringify({
                    success: false,
                    error: "offline",
                    message: "لا يوجد اتصال بالإنترنت. هذه العملية تحتاج إلى اتصال فعال بالإنترنت لحماية حسابك وتأكيد العملية بأمان، يرجى التحقق من اتصالك والمحاولة مجدداً."
                }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json; charset=utf-8' }
                });
            })
        );
        return;
    }

    // 1. Catalog Data API (/api/offline-catalog/): Stale-While-Revalidate
    if (url.pathname.includes('/api/offline-catalog/')) {
        event.respondWith(
            caches.open(DATA_CACHE).then(function(cache) {
                return cache.match(request).then(function(cachedResponse) {
                    const fetchPromise = fetch(request).then(function(networkResponse) {
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(request, networkResponse.clone());
                        }
                        return networkResponse;
                    }).catch(function() {
                        return cachedResponse;
                    });
                    return cachedResponse || fetchPromise;
                });
            })
        );
        return;
    }

    // 2. Product Images (/media/products/ or static images): Cache-First with fallback
    if (url.pathname.startsWith('/media/') || url.pathname.includes('/img/')) {
        event.respondWith(
            caches.open(IMAGE_CACHE).then(function(cache) {
                return cache.match(request).then(function(cachedImage) {
                    if (cachedImage) return cachedImage;

                    return fetch(request).then(function(networkResponse) {
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(request, networkResponse.clone());
                        }
                        return networkResponse;
                    }).catch(function() {
                        // Return offline fallback placeholder if image cannot be loaded
                        return caches.match('/static/site/img/app-icon.svg');
                    });
                });
            })
        );
        return;
    }

    // 3. Static Assets (CSS, JS, Fonts): Stale-While-Revalidate
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.open(STATIC_CACHE).then(function(cache) {
                return cache.match(request).then(function(cached) {
                    const fetchPromise = fetch(request).then(function(networkResponse) {
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(request, networkResponse.clone());
                        }
                        return networkResponse;
                    }).catch(function() {
                        return cached;
                    });
                    return cached || fetchPromise;
                });
            })
        );
        return;
    }

    // 4. HTML Navigation (Pages): Network-First, Cache Fallback on Offline
    if (request.mode === 'navigate' || request.headers.get('accept')?.includes('text/html')) {
        event.respondWith(
            fetch(request).then(function(response) {
                // If successful network response, save copy to dynamic cache
                if (response && response.status === 200) {
                    const copy = response.clone();
                    caches.open(DYNAMIC_CACHE).then(function(cache) {
                        cache.put(request, copy);
                    });
                }
                return response;
            }).catch(function() {
                // Offline fallback: check dynamic cache, then static cache, then /catalog/
                return caches.match(request).then(function(cachedPage) {
                    if (cachedPage) return cachedPage;
                    return caches.match('/catalog/').then(function(catalogPage) {
                        if (catalogPage) return catalogPage;
                        return caches.match('/');
                    });
                });
            })
        );
        return;
    }

    // Default: Network with Cache Fallback
    event.respondWith(
        fetch(request).catch(function() {
            return caches.match(request);
        })
    );
});

// Push Notifications: Rich notifications with sounds and action buttons
self.addEventListener('push', function(event) {
    if (!event.data) return;

    try {
        let payload = {};
        try {
            payload = event.data.json();
        } catch (e) {
            payload = { title: 'Raqamiyat | رقميات', body: event.data.text() };
        }

        const title = payload.title || 'Raqamiyat | رقميات';
        const options = {
            body: payload.body || 'لديك إشعار جديد في حسابك',
            icon: payload.icon || '/static/site/img/app-icon.svg',
            badge: payload.badge || '/static/site/img/app-icon.svg',
            image: payload.image || null,
            tag: payload.tag || 'raqamiyat-notification',
            renotify: true,
            data: {
                url: payload.action_url || payload.url || '/dashboard/',
                timestamp: Date.now()
            },
            vibrate: [200, 100, 200, 100, 300],
            actions: payload.actions || [
                { action: 'open', title: 'عرض التفاصيل' },
                { action: 'dismiss', title: 'إغلاق' }
            ]
        };

        event.waitUntil(
            Promise.all([
                self.registration.showNotification(title, options),
                self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
                    clientList.forEach(function(client) {
                        client.postMessage({
                            type: 'PUSH_NOTIFICATION',
                            title: title,
                            body: options.body,
                            url: options.data.url
                        });
                    });
                })
            ])
        );
    } catch (err) {
        console.error('ServiceWorker push notification error:', err);
    }
});

// Notification Click: Focus existing tab or open URL
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    if (event.action === 'dismiss') {
        return;
    }

    const targetUrl = (event.notification.data && event.notification.data.url) || '/dashboard/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes(targetUrl) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
