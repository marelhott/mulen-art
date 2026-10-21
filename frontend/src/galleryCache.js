// The gallery (history + library lists) is kept in the browser's IndexedDB so a reload shows it at once,
// even while the server is still waking up. The network answer then replaces it (stale-while-revalidate).
const DB_NAME = "img2img-cache";
const STORE = "kv";
export const GALLERY_CACHE_KEY = "gallery-v1";

function openDatabase() {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    } catch {
      resolve(null); // private mode / blocked storage: the app works without the cache
    }
  });
}

export async function readCached(key) {
  const db = await openDatabase();
  if (!db) return null;
  return new Promise((resolve) => {
    try {
      const request = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
      request.onsuccess = () => resolve(request.result ?? null);
      request.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

export async function writeCached(key, value) {
  const db = await openDatabase();
  if (!db) return false;
  return new Promise((resolve) => {
    try {
      const transaction = db.transaction(STORE, "readwrite");
      transaction.objectStore(STORE).put(value, key);
      transaction.oncomplete = () => resolve(true);
      transaction.onerror = () => resolve(false);
      transaction.onabort = () => resolve(false);
    } catch {
      resolve(false);
    }
  });
}

// Only persisted outputs belong in the cache (they have a URL on the server); live in-memory results do not.
export function cacheableItems(items) {
  return (items || []).filter((item) => item && item.id && typeof item.url === "string" && item.url.startsWith("/"));
}
