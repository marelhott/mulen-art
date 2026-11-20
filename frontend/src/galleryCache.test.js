// Run: node --test frontend/src/galleryCache.test.js
import { test } from "node:test";
import assert from "node:assert/strict";

// A tiny in-memory IndexedDB: just enough of open / transaction / get / put / deleteDatabase.
function installFakeIndexedDB() {
  const data = new Map();
  let opens = 0;
  globalThis.indexedDB = {
    open() {
      opens += 1;
      const db = {
        close() {},
        transaction() {
          const transaction = {};
          return Object.assign(transaction, {
            objectStore: () => ({
              get(key) { const request = {}; queueMicrotask(() => { request.result = data.get(key); request.onsuccess?.(); }); return request; },
              put(value, key) { data.set(key, value); queueMicrotask(() => transaction.oncomplete?.()); },
            }),
          });
        },
      };
      const request = { result: db };
      queueMicrotask(() => { request.onupgradeneeded?.(); request.onsuccess?.(); });
      db.createObjectStore = () => {};
      request.result.createObjectStore = () => {};
      return request;
    },
    deleteDatabase() {
      data.clear();
      const request = {};
      queueMicrotask(() => request.onsuccess?.());
      return request;
    },
  };
  return { data, opens: () => opens };
}

test("cacheableItems keeps only persisted outputs", async () => {
  const { cacheableItems } = await import("./galleryCache.js");
  const kept = cacheableItems([null, { id: "a", url: "/library/a.png" }, { id: "b", url: "data:image/png;base64,AA" }, { url: "/x" }, { id: "c" }]);
  assert.deepEqual(kept.map((item) => item.id), ["a"]);
  assert.deepEqual(cacheableItems(undefined), []);
});

test("values round-trip, one connection is reused, and clearing wipes them", async () => {
  const fake = installFakeIndexedDB();
  const { readCached, writeCached, clearAllCached } = await import("./galleryCache.js");
  assert.equal(await readCached("k"), null);
  assert.equal(await writeCached("k", { n: 1 }), true);
  assert.deepEqual(await readCached("k"), { n: 1 });
  assert.equal(fake.opens(), 1);
  await clearAllCached();
  assert.equal(await readCached("k"), null);
});

test("without IndexedDB the cache quietly does nothing", async () => {
  delete globalThis.indexedDB;
  const { readCached, writeCached, clearAllCached } = await import("./galleryCache.js?nodb");
  assert.equal(await readCached("k"), null);
  assert.equal(await writeCached("k", 1), false);
  await clearAllCached();
});
