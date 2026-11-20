import { useEffect, useRef, useState } from "react";
import { apiFetch, readJson } from "./api";
import { GALLERY_CACHE_KEY, cacheableItems, readCached, writeCached } from "./galleryCache";

// The gallery: the saved library, the generation history (`results`, which also holds in-flight
// placeholders) and the ids the user deleted. It starts from the browser's last snapshot, then
// refreshes from the server.
export function useGallery() {
  const [results, setResults] = useState([]);
  const [libraryItems, setLibraryItems] = useState([]);
  const deletedIds = useRef(new Set());
  const galleryFresh = useRef(false);
  // True until the first snapshot (cached or fresh) or a failure: lets the UI show skeletons instead of "empty".
  const [loading, setLoading] = useState(true);
  // Ids that came from a server history listing: only those may be dropped when a later listing no
  // longer has them. Fresh results of this session are not in any listing yet and must stay.
  const fromHistory = useRef(new Set());

  // Shows a gallery snapshot (cached or fresh): library list, history list and deleted ids.
  function applyGallery(library, history, fresh = false) {
    for (const id of history?.deleted_ids || []) deletedIds.current.add(id);
    setLoading(false);
    setLibraryItems((library?.items || []).filter((item) => !deletedIds.current.has(item.id)));
    const incoming = history?.items || [];
    const incomingIds = new Set(incoming.map((item) => item.id));
    const gone = fresh ? new Set([...fromHistory.current].filter((id) => !incomingIds.has(id))) : new Set();
    for (const id of incomingIds) fromHistory.current.add(id);
    for (const id of gone) fromHistory.current.delete(id);
    setResults((current) => {
      const kept = current.filter((item) => !item || !gone.has(item.id));
      const ids = new Set(kept.filter(Boolean).map((item) => item.id));
      return [...kept, ...incoming.filter((item) => !ids.has(item.id))].filter((item) => !item || !deletedIds.current.has(item.id));
    });
  }

  async function loadLibrary() {
    // Both lists in parallel (they used to run one after the other, doubling the wait).
    const [libraryResponse, historyResponse] = await Promise.all([apiFetch("/api/library"), apiFetch("/api/history")]);
    const library = await readJson(libraryResponse, "Knihovnu se nepodařilo načíst.");
    const history = await readJson(historyResponse, "Historii se nepodařilo načíst.");
    galleryFresh.current = true;
    applyGallery(library, history, true);
    writeCached(GALLERY_CACHE_KEY, { library: { items: cacheableItems(library.items) }, history: { items: cacheableItems(history.items), deleted_ids: history.deleted_ids || [] }, savedAt: Date.now() });
  }

  // Keep the stored snapshot in step with what the user does (save, delete, new results), debounced.
  useEffect(() => {
    if (!galleryFresh.current) return undefined;
    const timer = window.setTimeout(() => {
      writeCached(GALLERY_CACHE_KEY, {
        library: { items: cacheableItems(libraryItems) },
        history: { items: cacheableItems(results), deleted_ids: [...deletedIds.current] },
        savedAt: Date.now(),
      });
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [libraryItems, results]);

  useEffect(() => {
    // Instant start: show the last known gallery from the browser while the server (possibly cold) answers.
    readCached(GALLERY_CACHE_KEY).then((cached) => {
      if (cached && !galleryFresh.current) applyGallery(cached.library, cached.history);
    });
    loadLibrary().catch(() => setLoading(false));
  }, []);

  return { results, setResults, libraryItems, setLibraryItems, deletedIds, loadLibrary, galleryLoading: loading };
}
