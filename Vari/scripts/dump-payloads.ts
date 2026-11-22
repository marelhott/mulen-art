// Parity oracle for the Python port (app_runtime/vari): runs the ORIGINAL TypeScript builders on a fixed grid of
// inputs and prints every provider payload. tests/test_vari.py must reproduce this file exactly.
// Run: cd Vari && npx --yes tsx scripts/dump-payloads.ts > ../tests/fixtures/vari_payloads.json
import { ENGINE_BUILDERS } from "../lib/engines/index";
import { DISTANCE_VALUES, ENGINE_VALUES } from "../lib/engines";
import { buildPrompt } from "../lib/prompts";
import { falImageSize, snappedDimensions, SUPPORTED_RATIOS } from "../lib/image-info";
import { buildGptImage2Prompt, buildVisionRemixPrompt } from "../lib/providers/openai";
import type { EngineContext } from "../lib/engines/types";
import type { ImageInfo } from "../lib/image-info";

Math.random = () => 0.5; // the Comfy workflows draw a random seed; Python receives the same fixed value

function info(width: number, height: number): ImageInfo {
  const ratio = width / height;
  const nearest = SUPPORTED_RATIOS.reduce((best, c) => (Math.abs(c.ratio - ratio) < Math.abs(best.ratio - ratio) ? c : best), SUPPORTED_RATIOS[0]);
  return { width, height, aspectRatio: nearest.value };
}

const IMAGES = [info(1500, 1000), info(1000, 1500), info(1024, 1024), info(1234, 987), info(736, 999), info(2000, 1000), info(1000, 2000)];
const TUNING: Array<Partial<EngineContext>> = [
  {},
  {
    comfyNoise: 0.3, comfyStrength: 0.5, ipAdapterScale: 0.7, ipAdapterSteps: 33.6, chigoScale: 0.6, chigoSteps: 51.4,
    sdxlGuidance: 4.1, sdxlStrength: 0.77, sdxlSteps: 29.5, stableGuidance: 4.4, stableStrength: 0.55, stableSteps: 21.2,
    sdVariationGuidance: 3.9, sdVariationSteps: 17.7, fofrCfg: 3.3, fofrSteps: 37.5, fofrIpWeight: 0.7, zImageCreativity: 0.42,
  },
  { comfyNoise: 0.9, comfyStrength: 0.1 }, // clamped by the Comfy builder
];

const skip = new Set(["vision-remix", "gpt-image-2", "gemini-3-pro"]); // handled inline in the route, not by a builder
const payloads: unknown[] = [];
for (const engine of ENGINE_VALUES) {
  if (skip.has(engine)) continue;
  for (const distance of DISTANCE_VALUES) {
    for (const count of [1, 3, 6]) {
      IMAGES.forEach((imageInfo, imageIndex) => {
        TUNING.forEach((tuning, tuningIndex) => {
          const ctx: EngineContext = {
            sourceUrl: "https://example.test/source.png", comfyReferenceUrl: "https://example.test/ref.png",
            imageInfo, distance, count, ...tuning,
          };
          payloads.push({ engine, distance, count, imageIndex, tuningIndex, payload: ENGINE_BUILDERS[engine](ctx) });
        });
      });
    }
  }
}

const analysis = {
  subject: "S", scene: "SC", composition: "C", framing: "F", perspective: "P", palette: "PA", light: "L", medium: "M",
  texture: "T", mood: "MO", immutable_elements: ["a", "b"], variable_elements: ["c", "d"], summary: "SU",
};
const prompts = Object.fromEntries(DISTANCE_VALUES.map((d) => [d, {
  base: buildPrompt(d), gpt: buildGptImage2Prompt(d, analysis), remix: buildVisionRemixPrompt(d, analysis),
}]));
const helpers = {
  falImageSize: IMAGES.map(falImageSize),
  snapped: IMAGES.map((i) => [snappedDimensions(i, 1024), snappedDimensions(i, 1280), snappedDimensions(i, 1344)]),
  aspect: IMAGES.map((i) => i.aspectRatio),
};
process.stdout.write(JSON.stringify({ images: IMAGES, analysis, prompts, helpers, payloads }) + "\n");
