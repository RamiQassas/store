/*
 * Raqamiyat Web Push Client
 * Registers service worker and handles browser subscriptions
 */

async function registerPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.warn('Push messaging is not supported in this browser.');
        return;
    }

    const publicKey = window.VAPID_PUBLIC_KEY;
    if (!publicKey) {
        console.error("VAPID Public Key missing.");
        return;
    }

    try {
        const registration = await navigator.serviceWorker.register('/static/site/js/sw.js', { scope: '/' });
        console.log('Service Worker registered');

        // Check if already subscribed
        let subscription = await registration.pushManager.getSubscription();
        
        if (!subscription) {
            // Check permission first
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                console.warn('Notification permission denied');
                return;
            }

            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKey)
            });
            
            console.log('User subscribed to Push');
            await saveSubscription(subscription);
        } else {
            console.log('User already has a push subscription');
            // Optionally update it on the server
            await saveSubscription(subscription);
        }
    } catch (err) {
        console.error('Push Registration Error:', err);
    }
}

async function saveSubscription(subscription) {
    const data = subscription.toJSON();
    await fetch('/api/notifications/subscribe/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            endpoint: data.endpoint,
            p256dh: data.keys.p256dh,
            auth: data.keys.auth,
            browser: navigator.userAgent
        })
    });
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Trigger on load if authenticated
if (window.isUserAuthenticated) {
    window.addEventListener('load', () => {
        setTimeout(registerPush, 2000); // Delay to not block main thread
    });
}
