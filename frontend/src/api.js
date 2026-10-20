// Single place that knows how media URLs are built for the studio.
// import.meta.env exists under Vite; the optional chain keeps this module importable in plain Node tests.
export const API_URL = import.meta.env?.VITE_API_URL || "";

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
