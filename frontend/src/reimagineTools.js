// Presets for the unCLIP tab: one input image becomes several versions at once, one per preset (same seed, so they compare fairly).
export const REIMAGINE_PRESETS = [
  {id: "faithful", name: "Věrná", denoise: 0.5, noise: 0},
  {id: "balanced", name: "Střední", denoise: 0.65, noise: 0},
  {id: "free", name: "Volná", denoise: 0.8, noise: 0},
  {id: "loose", name: "Střední + odchylka", denoise: 0.65, noise: 150},
];

// The requests sent for ONE input image. Manual mode: chunks of up to 8 images with consecutive seeds.
// Preset mode: one image per preset, all with the same seed.
export function planReimagine({count, strength, noise, seed, usePresets}) {
  if (usePresets) return REIMAGINE_PRESETS.map(preset => ({denoise: preset.denoise, noise_level: preset.noise, num_images: 1, seed, preset: preset.id}));
  return Array.from({length: Math.ceil(count / 8)}, (_, chunk) => ({denoise: strength, noise_level: noise, num_images: Math.min(8, count - chunk * 8), seed: (seed + chunk * 8) % 4294967296}));
}

export const plannedImages = plan => plan.reduce((sum, request) => sum + request.num_images, 0);
