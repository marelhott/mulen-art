// Single place that knows how media URLs are built for the studio.
// import.meta.env exists under Vite; the optional chain keeps this module importable in plain Node tests.
import { clearAllCached } from "./galleryCache.js";

export const API_URL = import.meta.env?.VITE_API_URL || "";

export function reconcileOptionIds(current, options, fallbackId) {
  const valid = current.filter(id => options.some(option => option.id === id));
  return valid.length ? valid : options.length ? [fallbackId ?? options[0].id] : current;
}

const ABSOLUTE = /^(https?:|data:|blob:)/;

export function buildImageUrl(path) {
  if (!path) return "";
  if (ABSOLUTE.test(path)) return path;
  return `${API_URL}${path}`;
}

/**
 * Small WebP preview for grids. In-memory results from a running job may not carry
 * thumb_url yet, so the path is derived from the stored filename instead of pulling
 * a full-resolution PNG into the gallery.
 */
export function thumbUrl(item) {
  if (!item) return "";
  if (item.thumb_url) return buildImageUrl(item.thumb_url);
  // Only stored results can be served from the thumbnail route; local uploads keep their blob URL.
  if (typeof item.url === "string" && item.url.startsWith("/library/")) {
    const stem = item.url.replace(/^\/library\//, "").replace(/\.[^.]+$/, "");
    return buildImageUrl(`/thumb/${stem}.webp`);
  }
  return imageUrl(item);
}

/** Full-resolution source for the viewer, download and export. */
export function imageUrl(item) {
  if (!item) return "";
  if (item.src) return item.src;
  if (item.url) return buildImageUrl(item.url);
  if (item.image_base64) return `data:image/${item.format || "png"};base64,${item.image_base64}`;
  return "";
}

export function sourceUrl(item) {
  const path = item?.source_url || item?.settings?.source_url;
  return path ? buildImageUrl(path) : "";
}

export function formatDuration(seconds) {
  const value = Number(seconds) || 0;
  return value < 60
    ? `${Math.floor(value)} s`
    : `${Math.floor(value / 60)} min ${Math.floor(value % 60)} s`;
}

/** Thrown when the server says the session is gone; local private data has already been purged. */
export class AuthError extends Error {}

/** Forget every private image this browser may still hold (Cache Storage and the IndexedDB gallery). */
export async function purgePrivateData() {
  try {
    if (typeof caches !== "undefined") {
      for (const key of await caches.keys()) if (key.startsWith("img2img-")) await caches.delete(key);
    }
  } catch { /* storage unavailable */ }
  await clearAllCached();
}

let signingOut = false;
async function leaveToLogin() {
  if (signingOut) return;
  signingOut = true;
  await purgePrivateData();
  window.location.assign("/login");
}

/** Explicit sign-out: ends the server session, then wipes local caches. */
export async function signOut() {
  let ended = false;
  try { ended = (await fetch(`${API_URL}/logout`, { method: "POST" })).ok; } catch { /* offline: still wipe locally */ }
  if (ended) return leaveToLogin();
  // A server without sessions (local dev) has nothing to log out of: just forget the cached images.
  await purgePrivateData();
  window.location.reload();
}

/** fetch() for the studio API: a 401 wipes private local data and goes to the login page. */
export async function apiFetch(path, options) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (response.status === 401) {
    await leaveToLogin();
    throw new AuthError("Přihlášení vypršelo.");
  }
  return response;
}

/** Parse a JSON body defensively: proxy error pages (502/503/504) are HTML, not JSON. */
export async function readJson(response, fallback = "Požadavek se nezdařil.") {
  let data = null;
  try { data = await response.json(); } catch { /* not JSON */ }
  if (!response.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : "";
    throw new Error(detail || `${fallback} (HTTP ${response.status})`);
  }
  if (data === null) throw new Error(`${fallback} (neplatná odpověď serveru)`);
  return data;
}
