import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

function loadWorker({ stored = new Map(), fetchImpl, failStorage = false } = {}) {
  const listeners = {};
  const cache = {
    match: async (request) => stored.get(request.url),
    put: async (request, response) => { stored.set(request.url, response); },
    keys: async () => [...stored.keys()].map((url) => ({ url })),
    delete: async (key) => stored.delete(key.url),
  };
  const context = {
    self: { location: { origin: "https://app.test" }, addEventListener: (type, fn) => { listeners[type] = fn; }, skipWaiting() {}, clients: { claim: async () => {} } },
    caches: { open: async () => { if (failStorage) throw new Error("denied"); return cache; } },
    fetch: fetchImpl,
    URL,
  };
  vm.runInNewContext(readFileSync(new URL("../public/sw.js", import.meta.url), "utf8"), context);
  return { listeners, stored };
}

async function dispatch(worker, url, method = "GET") {
  let responded;
  const pending = [];
  worker.listeners.fetch({ request: { url, method }, respondWith: (promise) => { responded = promise; }, waitUntil: (promise) => pending.push(promise) });
  const result = responded ? await responded : undefined;
  await Promise.all(pending);
  return { handled: Boolean(responded), result };
}

const imageResponse = (status = 200, type = "image/webp") => ({ status, redirected: false, headers: { get: () => type }, clone() { return this; } });

test("service worker serves cached thumbnails without touching the network", async () => {
  const stored = new Map([["https://app.test/thumb/a.webp", imageResponse()]]);
  const worker = loadWorker({ stored, fetchImpl: async () => { throw new Error("network must not be used"); } });
  const { handled, result } = await dispatch(worker, "https://app.test/thumb/a.webp");
  assert.equal(handled, true);
  assert.equal(result, stored.get("https://app.test/thumb/a.webp"));
});

test("service worker stores only real image responses and ignores everything else", async () => {
  const worker = loadWorker({ fetchImpl: async () => imageResponse() });
  await dispatch(worker, "https://app.test/library/b.png");
  assert.equal(worker.stored.has("https://app.test/library/b.png"), true);
  const html = loadWorker({ fetchImpl: async () => imageResponse(200, "text/html") });
  await dispatch(html, "https://app.test/thumb/c.webp");
  assert.equal(html.stored.size, 0);
  const missing = loadWorker({ fetchImpl: async () => imageResponse(404) });
  await dispatch(missing, "https://app.test/thumb/d.webp");
  assert.equal(missing.stored.size, 0);
  const other = loadWorker({ fetchImpl: async () => imageResponse() });
  assert.equal((await dispatch(other, "https://app.test/api/history")).handled, false);
  assert.equal((await dispatch(other, "https://app.test/thumb/e.webp", "POST")).handled, false);
  assert.equal((await dispatch(other, "https://elsewhere.test/thumb/e.webp")).handled, false);
});

test("service worker falls back to the network when Cache Storage is unavailable", async () => {
  const worker = loadWorker({ failStorage: true, fetchImpl: async () => "from-network" });
  assert.equal((await dispatch(worker, "https://app.test/thumb/f.webp")).result, "from-network");
});
