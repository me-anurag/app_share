// Service worker: makes AppShare installable, opens fast, and reconnects by itself.
// Static files are cached; pages are network-first; API calls and uploads are never cached.
// When the server (or the internet tunnel in front of it) is down, the page shows the
// offline screen, which keeps checking and reopens the app as soon as the server is back.
const VERSION = "appshare-v16";       // = "appshare-" + APP_VERSION in common.js
const SHELL = [
  "/static/style.css", "/static/looks.css", "/static/common.js", "/static/offline.html",
  "/static/icons/icon-192.png", "/static/icons/icon-512.png",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// A tunnel provider answers with its own error page when the laptop is offline.
function serverMissing(res) {
  return res.headers.has("ngrok-error-code") || res.status === 502 || res.status === 503 || res.status === 504;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then(res => (serverMissing(res) ? caches.match("/static/offline.html") : res))
        .catch(() => caches.match("/static/offline.html"))
    );
    return;
  }
  if ((url.pathname.startsWith("/static/") || url.pathname.startsWith("/agents/")) && url.searchParams.get("v")) {
    // A stamped file (?v=fingerprint) never changes: answer from the phone's cache instantly; fetch it only once.
    e.respondWith(caches.open(VERSION).then(async cache => {
      const hit = await cache.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok) cache.put(req, res.clone());
      return res;
    }));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    // Static files: always the latest from the server (so an update shows up on the next open, not the one after);
    // the saved copy is only used when the server can't be reached.
    e.respondWith(caches.open(VERSION).then(async cache => {
      try {
        const res = await fetch(req, { cache: "no-cache" });
        if (res.ok) cache.put(req, res.clone());
        return res;
      } catch {
        return (await cache.match(req)) || Response.error();
      }
    }));
  }
});
