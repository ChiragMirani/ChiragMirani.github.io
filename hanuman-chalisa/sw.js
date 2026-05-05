const CACHE = "hanuman-chalisa-v2";
const SHELL = [
  "./",
  "./index.html",
  "./about.html",
  "./data.json",
  "./static/styles.css",
  "./manifest.webmanifest",
  "./manifest-v2.webmanifest",
  "./apple-touch-icon.png",
  "./hanuman-app-icon-180.png",
  "./hanuman-app-icon-192.png",
  "./hanuman-app-icon-512.png",
  "./favicon-192.png",
  "./favicon-512.png",
  "./favicon-32.png",
  "./hanuman-favicon-32.png",
  "./favicon.ico",
  "./social-preview.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  if (request.headers.get("accept") && request.headers.get("accept").includes("text/html")) {
    event.respondWith(
      fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return response;
      }).catch(() => caches.match(request).then((match) => match || caches.match("./")))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
      return response;
    }))
  );
});
