// Service worker: приложение можно установить на телефон; оболочка сайта открывается без сети, API — всегда из сети.
const CACHE = 'us-shell-v2'
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/manifest.webmanifest', '/icon.svg'])))
  self.skipWaiting()
})
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))))
  self.clients.claim()
})
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return
  const page = e.request.mode === 'navigate'
  e.respondWith(
    fetch(page ? new Request(e.request, { cache: 'no-store' }) : e.request)
      .then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r })
      .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  )
})
