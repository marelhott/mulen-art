// The unCLIP tab has two modes:
//  - "unclip": SD 2.1 unCLIP around the noised source - faithful variations of the same picture.
//  - "metamorph": SDXL Base img2img + IP-Adapter - keeps layout, palette and gesture but re-invents the forms
//    (the behaviour of the old Clipdrop Reimagine XL). Defaults come from test grids on a real source.
export const REIMAGINE_MODES = [
  {id: "unclip", name: "Varianta", description: "Věrné varianty stejného obrazu (SD 2.1 unCLIP)."},
  {id: "metamorph", name: "Metamorfóza", description: "Drží kompozici, paletu a gesto, ale tvary přetváří v nové předměty (SDXL + IP-Adapter)."},
];

export const DEFAULT_REIMAGINE = {
  mode: "unclip", usePresets: false, count: 4, seed: "-1",
  strength: 0.6, noise: 0, steps: 35, cfg: 5, longSide: 1024,
  mStrength: 0.85, ipScale: 0.6, ipVariant: "plain", mSteps: 30, mCfg: 5.5,
};

// One input image becomes one version per preset, all with the same seed so they compare fairly.
export const REIMAGINE_PRESETS = {
  unclip: [
    {id: "faithful", name: "Věrná", settings: {denoise: 0.5, noise_level: 0}},
    {id: "balanced", name: "Střední", settings: {denoise: 0.65, noise_level: 0}},
    {id: "free", name: "Volná", settings: {denoise: 0.8, noise_level: 0}},
    {id: "loose", name: "Střední + odchylka", settings: {denoise: 0.65, noise_level: 150}},
  ],
  metamorph: [
    {id: "gentle", name: "Jemná", settings: {denoise: 0.75, ip_scale: 0.6}},
    {id: "classic", name: "Klasická", settings: {denoise: 0.85, ip_scale: 0.6}},
    {id: "anchored", name: "Ukotvená v obraze", settings: {denoise: 0.85, ip_scale: 0.8}},
    {id: "bold", name: "Odvážná", settings: {denoise: 0.92, ip_scale: 0.6}},
  ],
};

export function presetLabel(preset) {
  const s = preset.settings, number = value => String(value).replace(".", ",");
  return [preset.name, `síla ${number(s.denoise)}`, s.ip_scale !== undefined && `vliv obrazu ${number(s.ip_scale)}`, s.noise_level && `odchylka ${s.noise_level}`].filter(Boolean).join(" · ");
}

function modeSettings(r) {
  return r.mode === "metamorph"
    ? {reimagine_mode: "metamorph", denoise: Number(r.mStrength), ip_scale: Number(r.ipScale), ip_variant: r.ipVariant, steps: Number(r.mSteps), cfg: Number(r.mCfg)}
    : {reimagine_mode: "unclip", denoise: Number(r.strength), noise_level: Number(r.noise), long_side: Number(r.longSide), steps: Number(r.steps), cfg: Number(r.cfg)};
}

// The request settings sent for ONE input image. Manual mode: chunks of up to 8 images with consecutive seeds.
export function planReimagine(r, seed) {
  const base = {generation_type: "reimagine", ...modeSettings(r)};
  if (r.usePresets) return (REIMAGINE_PRESETS[r.mode] || REIMAGINE_PRESETS.unclip).map(preset => ({...base, ...preset.settings, num_images: 1, seed}));
  const count = Number(r.count);
  return Array.from({length: Math.ceil(count / 8)}, (_, chunk) => ({...base, num_images: Math.min(8, count - chunk * 8), seed: (seed + chunk * 8) % 4294967296}));
}

export const plannedImages = plan => plan.reduce((sum, request) => sum + request.num_images, 0);

// Back from a stored image's settings to the controls (the "repeat" action).
export function reimagineFromSettings(settings, current) {
  if (settings.reimagine_mode === "metamorph")
    return {...current, mode: "metamorph", mStrength: settings.denoise ?? current.mStrength, ipScale: settings.ip_scale ?? current.ipScale,
      ipVariant: settings.ip_variant ?? current.ipVariant, mSteps: settings.steps ?? current.mSteps, mCfg: settings.guidance_scale ?? settings.cfg ?? current.mCfg};
  return {...current, mode: "unclip", strength: settings.denoise ?? current.strength, noise: settings.noise_level ?? current.noise,
    longSide: settings.generation_height && settings.generation_width ? (Math.max(settings.generation_width, settings.generation_height) > 800 ? 1024 : 768) : current.longSide,
    steps: settings.steps ?? current.steps, cfg: settings.guidance_scale ?? settings.cfg ?? current.cfg};
}
