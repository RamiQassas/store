/* 
 * Raqamiyat Support Service Worker 
 * Handles background push notifications
 */

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
