import type { EngineBuilder } from "./types";

const STABLE_UNCLIP_VERSION =
  "3a8d2f4f25198c92beb3c633ed94f8013399509c7321cd09c9036c2e33c67617";

export const buildUnclipPayload: EngineBuilder = (ctx) => {
  return {
    _provider: "replicate",
    version: STABLE_UNCLIP_VERSION,
    input: {
      image: ctx.sourceUrl,
      num_outputs: ctx.count,
      num_inference_steps: ctx.distance === "new-frame" ? 60 : 50,
      guidance_scale: ctx.distance === "new-frame" ? 5.8 : 6.8,
      scheduler: "DPMSolverMultistep",
    },
  };
};
