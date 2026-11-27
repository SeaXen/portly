// Portly Progressive Web App Service Worker
const CACHE_NAME = 'portly-v5';
const MAX_ASSET_ENTRIES = 60;
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.ico',
  '/icons/icon.svg',
  '/icons/icon-32.png',
  '/icons/apple-touch-icon.png',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Exclude API calls and SSE stream
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/stream')) {
    return;
  }

  // Navigation requests: network first, fallback to cached index.html
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Static assets: cache first or stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const toCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(async (cache) => {
            await cache.put(event.request, toCache);
            // Hashed assets change every build; evict oldest so the cache
            // cannot grow without bound across deploys.
            const keys = await cache.keys();
            if (keys.length > MAX_ASSET_ENTRIES) {
              const excess = keys.length - MAX_ASSET_ENTRIES;
              await Promise.all(
                keys.slice(PRECACHE_URLS.length, PRECACHE_URLS.length + excess).map((k) => cache.delete(k))
              );
            }
          });
        }
        return networkResponse;
      });
    })
  );
});
