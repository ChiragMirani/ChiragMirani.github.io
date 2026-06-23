const CACHE_NAME = "upanishads-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./about.html",
  "./data.json?v=1",
  "./static/styles.css?v=1",
  "./static/app.js?v=1",
  "./favicon.svg?v=1",
  "./favicon-32.png?v=1",
  "./favicon-192.png?v=1",
  "./apple-touch-icon.png?v=1",
  "./upanishads-hero.png?v=1",
  "./social-preview.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached || fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      }).catch(() => caches.match("./index.html"))
    )
  );
});
