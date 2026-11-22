// Vari and Koláž (ported from Mulen Nano): which models, how far from the source, how many, and the request plan.
// A request is ONE model run: the server makes all its variants inside one job.
export const NANO_MAX_PER_MODEL = 5;
export const COLLAGE_MAX_SOURCES = 10;

export const NANO_DISTANCES = [
  {id: "near", name: "Blíž", hint: "Skoro stejná póza, jen jiný úhel"},
  {id: "middle", name: "Střed", hint: "Výchozí vzdálenost"},
  {id: "far", name: "Dál", hint: "Silně jiná póza a kompozice"},
  {id: "weird", name: "Divně", hint: "Podivný, snový, neobvyklý posun, stále stejná ruka"},
];

export const DEFAULT_VARI = {models: ["nano-pro"], distance: "middle", count: 3, prompt: ""};
export const DEFAULT_COLLAGE = {models: ["nano-pro"], fuse: true, count: 3, prompt: ""};

export const clampCount = value => Math.min(NANO_MAX_PER_MODEL, Math.max(1, Math.round(Number(value)) || 1));

// A model is usable when its provider key is set and it takes an input image (text-only models cannot make siblings or fusions).
export const takesImages = item => item.max_inputs !== 0;
// Models offered in the Koláž tab (Recraft takes one reference image, so it cannot fuse).
export const forCollage = item => item.collage !== false;

// The selected usable models, in catalogue order (a model never runs twice).
export function usableModels(selected, catalogue = []) {
  const chosen = new Set(selected || []);
  return catalogue.filter(item => chosen.has(item.id) && item.available && takesImages(item));
}

// Koláž fuses all inputs only when there are two or more and the switch is on; otherwise each input is worked on its own.
export const isFused = (collage, inputCount) => Boolean(collage.fuse) && inputCount >= 2;

export function planVari(state, catalogue) {
  const count = clampCount(state.count);
  return usableModels(state.models, catalogue).map(model => ({
    generation_type: "vari", nano_model: model.id, nano_distance: state.distance, num_images: count, prompt: String(state.prompt || "").trim()}));
}

// Koláž requests for `inputCount` stored sources. `uploadIds` are the stored source ids in input order.
// Fused: one request per model, the first source is the main input and the others travel as extra_source_ids.
// Each input on its own: one request per input and model, `count` variants each.
export function planCollage(state, catalogue, uploadIds, seedStart = 0) {
  const prompt = String(state.prompt || "").trim();
  const models = usableModels(state.models, catalogue.filter(forCollage));
  if (isFused(state, uploadIds.length)) {
    return models.map((model, index) => ({sourceIndex: 0, settings: {generation_type: "collage", nano_model: model.id, collage_fuse: true, num_images: 1, prompt,
      extra_source_ids: uploadIds.slice(1), seed: (seedStart + index) % 4294967296}}));
  }
  const count = clampCount(state.count);
  return uploadIds.flatMap((_, sourceIndex) => models.map((model, index) => ({sourceIndex, settings: {generation_type: "collage", nano_model: model.id,
    collage_fuse: false, num_images: count, prompt, seed: (seedStart + sourceIndex * 7 + index) % 4294967296}})));
}

export const plannedImages = plan => plan.reduce((sum, item) => sum + (item.settings ? item.settings.num_images : item.num_images), 0);

// Back from a stored image's settings to the controls (the "repeat" action).
export function variFromSettings(settings, current) {
  return {...current, models: settings.nano_model ? [settings.nano_model] : current.models, distance: settings.nano_distance || current.distance,
    prompt: settings.custom_prompt ?? current.prompt};
}

export function collageFromSettings(settings, current) {
  return {...current, models: settings.nano_model ? [settings.nano_model] : current.models, fuse: settings.collage_fuse ?? current.fuse,
    prompt: settings.custom_prompt ?? current.prompt};
}
