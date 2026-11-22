// Single source of truth for engine and distance constants.
// Import this everywhere (server + both client pages) so nothing drifts.

export type Distance = "locked" | "sibling" | "looser" | "new-frame";

export type Engine =
  | "gpt-image-2"
  | "gemini-3-pro"
  | "z-image"
  | "grok-imagine"
  | "sdxl-artistic"
  | "stable"
  | "sd-variation"
  | "vision-remix"
  | "unclip"
  | "comfy-unclip"
  | "ip-adapter-sdxl"
  | "chigozienri-ip-adapter-sdxl"
  | "fofr-any-comfyui-workflow";

export const DISTANCE_VALUES: Distance[] = ["locked", "sibling", "looser", "new-frame"];

export const ENGINE_VALUES: Engine[] = [
  "sd-variation",
  "gpt-image-2",
  "gemini-3-pro",
  "z-image",
  "grok-imagine",
  "vision-remix",
  "ip-adapter-sdxl",
  "fofr-any-comfyui-workflow",
  "chigozienri-ip-adapter-sdxl",
  "unclip",
  "comfy-unclip",
  "sdxl-artistic",
  "stable",
];

export const DISTANCE_COPY: Record<Distance, string> = {
  locked: "co nejblíž originálu",
  sibling: "další záběr ze stejné série",
  looser: "volnější, ale pořád příbuzné",
  "new-frame": "jiný záběr stejného světa",
};

export const ENGINE_COPY: Record<Engine, string> = {
  "gpt-image-2": "GPT Image 2",
  "gemini-3-pro": "Gemini 3 Pro",
  "z-image": "Z-Image",
  "grok-imagine": "Grok Imagine",
  "sdxl-artistic": "SDXL Artistic (exp)",
  stable: "Stable Variation (slow)",
  "sd-variation": "SD Image Variation",
  "vision-remix": "Vision Remix",
  unclip: "Stable unCLIP",
  "comfy-unclip": "Comfy IPAdapter",
  "ip-adapter-sdxl": "IP-Adapter SDXL",
  "fofr-any-comfyui-workflow": "fofr/any-comfyui-workflow",
  "chigozienri-ip-adapter-sdxl": "chigozienri/ip_adapter-sdxl",
};

export const ENGINE_ORDER: Engine[] = [
  "sd-variation",
  "gpt-image-2",
  "gemini-3-pro",
  "z-image",
  "grok-imagine",
  "vision-remix",
  "ip-adapter-sdxl",
  "chigozienri-ip-adapter-sdxl",
  "unclip",
  "comfy-unclip",
  "sdxl-artistic",
  "stable",
  "fofr-any-comfyui-workflow",
];

export const COMFY_DEFAULTS: Record<Distance, { noise: number; strength: number }> = {
  locked: { noise: 0.21, strength: 0.86 },
  sibling: { noise: 0.21, strength: 0.86 },
  looser: { noise: 0.21, strength: 0.86 },
  "new-frame": { noise: 0.21, strength: 0.86 },
};

// UI layout constants. Count cap for routes / generate-all safety.
export const GRID_COLS = 4;
export const GRID_ROWS = 3;
export const DEFAULT_EXPECTED_COUNT = GRID_COLS * GRID_ROWS;

export function isDistance(value: unknown): value is Distance {
  return typeof value === "string" && DISTANCE_VALUES.includes(value as Distance);
}

export function isEngine(value: unknown): value is Engine {
  return typeof value === "string" && ENGINE_VALUES.includes(value as Engine);
}
