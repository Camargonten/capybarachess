const CACHE_NAME = 'capybara-shell-v4';
const APP_SHELL = ['/static/manifest.webmanifest', '/static/capybara-icon.svg', '/static/capybara-custom.css',
    '/static/icons/icon-192.png', '/static/icons/icon-512.png'];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).catch(() => {})
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(
            keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(async () => (await caches.match('/')) || Response.error())
        );
        return;
    }
    if (APP_SHELL.some(path => request.url.endsWith(path))) {
        event.respondWith(
            caches.match(request).then(cached => cached || fetch(request))
        );
    }
});
