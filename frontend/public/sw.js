// Media cache: generated images never change under their file name, so thumbnails and full images are
// served from the browser's Cache Storage first. A reload therefore does not wait for the server at all.
// Thumbnails (small, plentiful) and full-size originals (5-20 MB each) live in separate caches with
// separate limits, so a few big PNGs can never push the browser into evicting this whole origin.
const THUMBS = "img2img-thumbs-v2";
const FULL = "img2img-full-v2";
const LIMITS = { [THUMBS]: 4000, [FULL]: 150 };
const TRIM_EVERY = 25;
const puts = { [THUMBS]: 0, [FULL]: 0 };

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  // Older versions of this worker used other cache names; drop them (and with them any stale entries).
  for (const key of await caches.keys()) {
    if (key.startsWith("img2img-") && key !== THUMBS && key !== FULL) await caches.delete(key);
  }
  await self.clients.claim();
})()));

async function trim(cache, limit) {
  const keys = await cache.keys();
  if (keys.length > limit) await Promise.all(keys.slice(0, keys.length - limit + Math.min(200, limit >> 2)).map((key) => cache.delete(key)));
}

// `?retry=N` only forces the browser to retry a failed load; it must not create a second cache entry.
function cacheKey(request) {
  const url = new URL(request.url);
  url.searchParams.delete("retry");
  return url.toString();
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  const match = /^\/(thumb|library)\//.exec(url.pathname);
  if (url.origin !== self.location.origin || !match) return;
  const name = match[1] === "thumb" ? THUMBS : FULL;
  event.respondWith((async () => {
    let cache;
    try {
      cache = await caches.open(name);
      const hit = await cache.match(cacheKey(request));
      if (hit) return hit;
    } catch {
      return fetch(request); // storage unavailable: behave as if there were no service worker
    }
    const response = await fetch(request);
    if (response.status === 401) {
      // The session is gone: never keep serving private images from this browser.
      event.waitUntil(Promise.all([caches.delete(THUMBS), caches.delete(FULL)]).catch(() => {}));
      return response;
    }
    const type = response.headers.get("content-type") || "";
    // Only real images: never cache an error page, a login redirect or a partial response.
    if (response.status === 200 && !response.redirected && type.startsWith("image/")) {
      event.waitUntil(cache.put(cacheKey(request), response.clone()).then(async () => {
        puts[name] += 1;
        if (puts[name] % TRIM_EVERY === 0) await trim(cache, LIMITS[name]);
      }).catch(() => {})); // quota exceeded and the like: the image simply is not cached
    }
    return response;
  })());
});
