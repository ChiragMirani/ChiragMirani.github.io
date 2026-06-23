const CACHE_NAME = "vedas-reader-v18";
const CORE_ASSETS = [
  "./",
  "./index.html",
  "./about.html",
  "./data.json?v=18",
  "./static/styles.css?v=18",
  "./manifest.webmanifest?v=18",
  "./favicon.svg?v=18",
  "./favicon.ico?v=18",
  "./favicon-32.png?v=18",
  "./favicon-192.png?v=18",
  "./favicon-512.png?v=18",
  "./apple-touch-icon.png?v=18",
  "./veda-hero.png?v=18",
  "./social-preview.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
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
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request).then((cached) => cached || caches.match("./index.html")))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    })
  );
});
