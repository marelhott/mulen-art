import type { EngineBuilder } from "./types";

const SD_IMAGE_VARIATION_VERSION =
  "7c399ba0e1b33ed8ec39ed30eb6b0a2d9e054462543c428c251293034af82a8e";

export const buildSdVariationPayload: EngineBuilder = (ctx) => {
  return {
    _provider: "replicate",
    version: SD_IMAGE_VARIATION_VERSION,
    input: {
      input_image: ctx.sourceUrl,
      num_outputs: Math.max(1, Math.min(4, Math.round(ctx.count))),
      num_inference_steps: typeof ctx.sdVariationSteps === "number" ? Math.round(ctx.sdVariationSteps) : 25,
      guidance_scale:
        typeof ctx.sdVariationGuidance === "number"
          ? ctx.sdVariationGuidance
          : ctx.distance === "locked"
            ? 3.4
            : ctx.distance === "sibling"
              ? 3
              : ctx.distance === "looser"
                ? 2.7
                : 2.4,
    },
  };
};
