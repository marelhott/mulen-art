import { TEXT } from "./texts.js";

// Library/canvas filter: by model and by free text over prompt, subject, source name and seed.
export function filterItems(items, { modelId = "", text = "" } = {}) {
  const needle = text.trim().toLowerCase();
  if (!modelId && !needle) return items;
  return items.filter((item) => {
    if (!item) return false;
    const settings = item.settings || {};
    if (modelId && (item.model_id || settings.model_id) !== modelId) return false;
    if (!needle) return true;
    return [settings.prompt, settings.subject_title, settings.source_name, settings.seed, item.filename]
      .some((field) => field !== undefined && field !== null && String(field).toLowerCase().includes(needle));
  });
}

// Real per-job GPU seconds from finished images; the first image of a job is the cleanest sample.
export function averageWorkerSeconds(items, limit = 30) {
  const samples = items
    .map((item) => item?.settings?.worker_seconds)
    .filter((value) => Number.isFinite(value) && value > 0)
    .slice(0, limit);
  return samples.length ? samples.reduce((sum, value) => sum + value, 0) / samples.length : null;
}

export function etaSeconds({ remainingJobs, parallel = 10, averageSeconds }) {
  if (!averageSeconds || remainingJobs <= 0) return null;
  return Math.ceil(remainingJobs / parallel) * averageSeconds;
}

export function formatEta(seconds) {
  if (seconds < 90) return `${Math.max(5, Math.round(seconds / 5) * 5)} s`;
  return `${Math.round(seconds / 60)} min`;
}

export function etaLabel(args) {
  const seconds = etaSeconds(args);
  return seconds === null ? "" : TEXT.eta(formatEta(seconds));
}

export function usageLabel(usage) {
  if (!usage || usage.spent_usd === null || usage.spent_usd === undefined) return "";
  return usage.budget_usd ? TEXT.budget(usage.spent_usd, usage.budget_usd) : TEXT.spentOnly(usage.spent_usd);
}

// Maps a stored image's generation settings back onto the studio controls ("repeat with these settings").
export function controlsFromSettings(settings = {}) {
  const has = (value) => value !== undefined && value !== null;
  const engine = {};
  const copy = [["mode", "render_mode"], ["conditioningMode", "conditioning_mode"], ["sampler", "sampler"],
    ["schedule", "schedule"], ["prompt", "prompt"], ["negativePrompt", "negative_prompt"], ["maxSide", "max_side"],
    ["detailStrength", "detail_strength"], ["detailSteps", "detail_steps"]];
  for (const [target, source] of copy) if (has(settings[source])) engine[target] = settings[source];
  if (has(settings.seed)) engine.seed = String(settings.seed);
  const controls = { engine };
  if (settings.model_id) controls.modelId = settings.model_id;
  if (settings.lora_id) controls.loraId = settings.lora_id;
  if (has(settings.lora_strength)) controls.loraStrength = settings.lora_strength;
  if (has(settings.denoise)) controls.denoise = settings.denoise;
  const cfg = settings.cfg ?? settings.guidance_scale;
  if (has(cfg)) controls.cfg = cfg;
  if (has(settings.steps)) controls.steps = settings.steps;
  return controls;
}

const ATELIER_MODES = { noise: "Volná studie", subject: "Automatický námět", photo: "Foto → malba", archive: "Archiv → fúze" };

// How an output was made: one of the four Atelier modes, or empty for ordinary img2img results.
export function creationMode(item) {
  const settings = item?.settings || {};
  return settings.generation_type === "atelier" ? ATELIER_MODES[settings.atelier_mode] || "Ateliér" : "";
}

// Delays before re-requesting an image that failed to load (a fresh output may not be visible yet).
export const RETRY_DELAYS_MS = [800, 2000, 5000];

export function retryUrl(src, attempt) {
  if (!src || attempt === 0 || /^(data:|blob:)/.test(src)) return src;
  return `${src}${src.includes("?") ? "&" : "?"}retry=${attempt}`;
}
