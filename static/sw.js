const CACHE_NAME = 'capybara-shell-v2';
const APP_SHELL = ['/static/manifest.webmanifest', '/static/capybara-icon.svg'];

self.addEventListener('install', event => {
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => Promise.all(keys.map(key => caches.delete(key))))
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;

    // Navegação sempre busca a versão mais recente do servidor (Network First)
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(async () => (await caches.match('/')) || Response.error())
        );
        return;
    }
});
