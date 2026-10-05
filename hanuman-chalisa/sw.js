const CACHE = "hanuman-chalisa-v4";
const SHELL = [
  "./",
  "./index.html",
  "./about.html",
  "./app.html",
  "./privacy.html",
  "./support.html",
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
  // Only handle this site's own files. Anything else goes straight to the network.
  if (new URL(request.url).origin !== self.location.origin) return;

  // Keep a copy of a good answer so the page can open offline next time.
  // A failed answer (like a 404) is not worth keeping.
  const remember = (response) => {
    if (response && response.ok) {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
    }
    return response;
  };

  if (request.headers.get("accept") && request.headers.get("accept").includes("text/html")) {
    // Pages: try the network first so updates show up, fall back to the saved copy.
    event.respondWith(
      fetch(request).then(remember).catch(() => caches.match(request).then((match) => match || caches.match("./")))
    );
    return;
  }

  // Everything else: the saved copy first, then the network. If both fail, say
  // so plainly instead of leaving an unhandled error in the console.
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then(remember)).catch(() => Response.error())
  );
});
