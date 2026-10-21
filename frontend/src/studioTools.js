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

// ---- Checkpoint mixes -------------------------------------------------------------------------
// A mix is addressed by its id alone ("mix:mulen_mara=60,tuymans_modal_2400=40"), so every place that
// takes a model id (canvas, Atelier modes, presets, comparison) accepts it without special handling.
export const MIX_MIN = 2;
export const MIX_MAX = 4;
const MIX_ID = /^mix:[a-z0-9_]+=\d{1,3}(,[a-z0-9_]+=\d{1,3}){1,3}$/;

export const isMixId = (id) => typeof id === "string" && id.startsWith("mix:");

export function parseMixId(id) {
  if (!MIX_ID.test(id || "")) return null;
  const parts = id.slice(4).split(",").map((part) => {
    const [partId, weight] = part.split("=");
    return { id: partId, weight: Number(weight) };
  });
  const total = parts.reduce((sum, part) => sum + part.weight, 0);
  const distinct = new Set(parts.map((part) => part.id)).size === parts.length;
  return total === 100 && distinct && parts.every((part) => part.weight >= 1) ? parts : null;
}

// Raw slider values -> whole percents that sum to exactly 100 (largest remainder, never below 1).
export function normalizeWeights(raw) {
  const total = raw.reduce((sum, value) => sum + value, 0);
  if (!raw.length || total <= 0) return raw.map(() => 0);
  const exact = raw.map((value) => (value * 100) / total);
  const result = exact.map((value) => Math.max(1, Math.floor(value)));
  let missing = 100 - result.reduce((sum, value) => sum + value, 0);
  const order = exact.map((value, index) => ({ index, rest: value - Math.floor(value) })).sort((a, b) => b.rest - a.rest);
  for (let i = 0; missing > 0; i = (i + 1) % order.length, missing -= 1) result[order[i].index] += 1;
  for (; missing < 0; missing += 1) {
    const biggest = result.indexOf(Math.max(...result));
    result[biggest] -= 1;
  }
  return result;
}

export function buildMixId(parts) {
  const weights = normalizeWeights(parts.map((part) => part.weight));
  return `mix:${parts.map((part, index) => `${part.id}=${weights[index]}`).join(",")}`;
}

// Selector entry for a mix, or null when it refers to a checkpoint this server does not have.
export function mixEntry(id, models) {
  const parts = parseMixId(id);
  if (!parts) return null;
  const named = parts.map((part) => ({ ...part, name: models.find((model) => model.id === part.id && model.kind !== "base")?.name }));
  if (named.some((part) => !part.name)) return null;
  return { id, name: `Fúze: ${named.map((part) => `${part.name} ${part.weight} %`).join(" + ")}`, kind: "mix", parts: named };
}

export function mixName(parts, models) {
  return parts.map((part) => `${models.find((model) => model.id === part.id)?.name || part.id} ${part.weight} %`).join(" + ");
}

export const MIX_STORAGE_KEY = "img2img-mixes-v1";

// Plain checkpoints and fusions are two exclusive ways of choosing models: the picker shows one source
// at a time and generation uses only the ids that belong to the active source.
export const sourceOf = (id) => (isMixId(id) ? "mix" : "single");
export const idsForSource = (ids, source) => ids.filter((id) => sourceOf(id) === source);
