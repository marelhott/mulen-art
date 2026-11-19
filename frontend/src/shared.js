import { formatDuration, imageUrl, sourceUrl, thumbUrl } from "./api";

export const urlFor = imageUrl;
export const sourceFor = sourceUrl;
export const thumbFor = thumbUrl;
export const duration = formatDuration;
export const dateFor = (date) =>
  date
    ? new Date(date).toLocaleString("cs-CZ", {
        day: "numeric",
        month: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

// localStorage throws in private mode or when site data is blocked; it is only ever a convenience.
export const safeStorage = {
  get(key) { try { return window.localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { window.localStorage.setItem(key, value); return true; } catch { return false; } },
  remove(key) { try { window.localStorage.removeItem(key); } catch { /* ignore */ } },
};

// crypto.randomUUID needs a secure context; a LAN dev server over plain http (vite --host) lacks it.
export function randomId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = (typeof crypto !== "undefined" && crypto.getRandomValues) ? crypto.getRandomValues(new Uint8Array(16)) : Array.from({length: 16}, () => Math.floor(Math.random() * 256));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
