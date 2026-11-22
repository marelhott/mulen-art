// Vari: variations through fal, Replicate, OpenAI and Gemini (the former standalone Vari app, now a studio tab).
export const VARI_DISTANCES = [
  {id: "locked", name: "Těsně", hint: "co nejblíž originálu"},
  {id: "sibling", name: "Sourozenec", hint: "další záběr ze stejné série"},
  {id: "looser", name: "Volněji", hint: "volnější, ale pořád příbuzné"},
  {id: "new-frame", name: "Nový", hint: "jiný záběr stejného světa"},
];

export const DEFAULT_VARI = {engineId: "sd-variation", allEngines: false, distance: "sibling", allDistances: false, count: 4, tuning: {}};

// Provider calls return at most this many images (the engine builders clamp them); more than that needs more calls.
const MAX_PER_CALL = {"sd-variation": 4, "z-image": 4, "grok-imagine": 4, "ip-adapter-sdxl": 4, "chigozienri-ip-adapter-sdxl": 4,
  "gpt-image-2": 4, "gemini-3-pro": 4, "vision-remix": 4};
export const maxPerCall = engineId => MAX_PER_CALL[engineId] ?? 12;

// Engines that can run now, in the server's order. `all` mode takes every one of them.
export const availableEngines = engines => (engines || []).filter(engine => engine.available);

// The requests sent for ONE input image: engines x distances x chunks of one provider call each.
export function planVari(state, engines) {
  const usable = availableEngines(engines);
  const chosen = state.allEngines ? usable : usable.filter(engine => engine.id === state.engineId);
  const distances = state.allDistances ? VARI_DISTANCES.map(item => item.id) : [state.distance];
  const requests = [];
  for (const engine of chosen) {
    const tuning = Object.fromEntries(engine.tuning.map(item => item.key).filter(key => Number.isFinite(state.tuning[key])).map(key => [key, state.tuning[key]]));
    const chunk = maxPerCall(engine.id);
    for (const distance of distances) {
      for (let done = 0; done < state.count; done += chunk) {
        requests.push({generation_type: "vari", vari_engine: engine.id, vari_distance: distance, num_images: Math.min(chunk, state.count - done), vari_tuning: tuning});
      }
    }
  }
  return requests;
}

export const plannedVariImages = requests => requests.reduce((sum, request) => sum + request.num_images, 0);

// Back from a stored image's settings (the "repeat" action).
export function variFromSettings(settings, current) {
  return {...current, engineId: settings.vari_engine ?? current.engineId, allEngines: false, distance: settings.vari_distance ?? current.distance,
    allDistances: false, tuning: settings.tuning && typeof settings.tuning === "object" ? settings.tuning : {}};
}
