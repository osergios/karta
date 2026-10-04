/* Work card service worker.
   Network-first for everything, so an online kiosk always gets the latest version;
   the precached shell only serves when the network is down (the page then shows
   "no connection - use the ERGANI app"). API and admin are never cached. */
"use strict";
const CACHE = "workcard-shell-v26";
const SHELL = [
  "/", "/enroll",
  "/static/style.css", "/static/kiosk.js", "/static/enroll.js", "/static/vendor/jsQR.min.js",
  "/brand.css", "/static/festive.js", "/static/brand/icons/icon-192.png",
  "/static/brand/fonts/inter-greek-300-normal.woff2", "/static/brand/fonts/inter-latin-300-normal.woff2",
  "/static/brand/fonts/inter-greek-400-normal.woff2", "/static/brand/fonts/inter-latin-400-normal.woff2",
  "/static/brand/fonts/inter-greek-500-normal.woff2", "/static/brand/fonts/inter-latin-500-normal.woff2",
  "/static/brand/fonts/inter-greek-600-normal.woff2", "/static/brand/fonts/inter-latin-600-normal.woff2",
];

self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", ev => {
  ev.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim()));
});

self.addEventListener("fetch", ev => {
  const req = ev.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin") || url.pathname.startsWith("/c/") || url.pathname === "/healthz") return;
  ev.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(async () => (await caches.match(req, { ignoreSearch: true }))
        || (req.mode === "navigate" ? caches.match("/") : Response.error())));
});

// Clicking a Windows notification brings the kiosk window to the front.
self.addEventListener("notificationclick", ev => {
  ev.notification.close();
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true })
    .then(wins => (wins.length ? wins[0].focus() : self.clients.openWindow("/"))));
});
