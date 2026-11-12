// Kalima offline support. The cache name below changes automatically each time the site is rebuilt,
// so visitors get new data on their next visit and old copies are deleted.
const VERSION = 'kalima-e82df0a4c11c';
const SHELL = ['./', 'index.html', 'vendor/compromise.js', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];

const DATA = ['data/ewt.txt', 'data/gum.txt', 'data/books.txt', 'data/pud.txt', 'data/model.json'];

self.addEventListener('install', e => {
  // the page itself must be saved; the data files are saved too when possible (the browser usually has them already)
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL).then(() => Promise.allSettled(DATA.map(f => c.add(f)))))
    .then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const own = url.origin === self.location.origin;
  const fonts = /^fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  if (!own && !fonts) return;
  if (req.mode === 'navigate') {
    // the page: try the network first so updates arrive, fall back to the saved copy offline
    e.respondWith(fetch(req).then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put('index.html', copy)); return r; })
      .catch(() => caches.match('index.html')));
    return;
  }
  // data, model, library, icons and fonts: use the saved copy, fetch and save it the first time
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
    if (r.ok || r.type === 'opaque') { const copy = r.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
    return r;
  })));
});
