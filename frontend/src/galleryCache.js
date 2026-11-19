// The gallery (history + library lists) is kept in the browser's IndexedDB so a reload shows it at once,
// even while the server is still waking up. The network answer then replaces it (stale-while-revalidate).
const DB_NAME = "img2img-cache";
const STORE = "kv";
export const GALLERY_CACHE_KEY = "gallery-v1";

// One connection is opened lazily and reused; opening a new one per read/write leaked handles.
let databasePromise = null;

function openDatabase() {
  if (!databasePromise) {
    databasePromise = new Promise((resolve) => {
      try {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => request.result.createObjectStore(STORE);
        request.onsuccess = () => {
          const db = request.result;
          db.onversionchange = () => { db.close(); databasePromise = null; };
          resolve(db);
        };
        request.onerror = () => resolve(null);
        request.onblocked = () => resolve(null);
      } catch {
        resolve(null); // private mode / blocked storage: the app works without the cache
      }
    }).then((db) => {
      if (!db) databasePromise = null; // allow a later retry
      return db;
    });
  }
  return databasePromise;
}

/** Remove everything this app keeps in IndexedDB (sign-out, expired session). */
export async function clearAllCached() {
  try {
    const db = await openDatabase();
    if (db) db.close();
    databasePromise = null;
    await new Promise((resolve) => {
      const request = indexedDB.deleteDatabase(DB_NAME);
      request.onsuccess = request.onerror = request.onblocked = () => resolve();
    });
  } catch { /* nothing cached or storage unavailable */ }
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
