// Media cache: generated images never change under their file name, so thumbnails and full images are
// served from the browser's Cache Storage first. A reload therefore does not wait for the server at all.
const CACHE = "img2img-media-v1";
const MAX_ENTRIES = 4000;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

async function trim(cache) {
  const keys = await cache.keys();
  if (keys.length > MAX_ENTRIES) await Promise.all(keys.slice(0, keys.length - MAX_ENTRIES + 200).map((key) => cache.delete(key)));
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !/^\/(thumb|library)\//.test(url.pathname)) return;
  event.respondWith((async () => {
    let cache;
    try {
      cache = await caches.open(CACHE);
      const hit = await cache.match(request);
      if (hit) return hit;
    } catch {
      return fetch(request); // storage unavailable: behave as if there were no service worker
    }
    const response = await fetch(request);
    const type = response.headers.get("content-type") || "";
    // Only real images: never cache an error page, a login redirect or a partial response.
    if (response.status === 200 && !response.redirected && type.startsWith("image/")) {
      event.waitUntil(cache.put(request, response.clone()).then(() => trim(cache)).catch(() => {}));
    }
    return response;
  })());
});
