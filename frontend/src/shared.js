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
