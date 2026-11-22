import type { EngineBuilder } from "./types";

const CHIGOZIENRI_IP_ADAPTER_SDXL_VERSION =
  "904dc004af1dba5c9b13fc9e41635aeb2f9a177896a396ab3393f3f6493dbdd4";

export const buildChigozienriIpAdapterSdxlPayload: EngineBuilder = (ctx) => {
  const numOutputs = Math.min(ctx.count, 4);
  const scale =
    typeof ctx.chigoScale === "number"
      ? ctx.chigoScale
      : ctx.distance === "locked"
        ? 0.92
        : ctx.distance === "sibling"
          ? 0.82
          : ctx.distance === "looser"
            ? 0.68
            : 0.54;

  const steps =
    typeof ctx.chigoSteps === "number"
      ? Math.round(ctx.chigoSteps)
      : ctx.distance === "locked"
        ? 80
        : ctx.distance === "sibling"
          ? 68
          : ctx.distance === "looser"
            ? 58
            : 48;

  return {
    _provider: "replicate",
    version: CHIGOZIENRI_IP_ADAPTER_SDXL_VERSION,
    input: {
      image: ctx.sourceUrl,
      prompt: "",
      negative_prompt: "",
      num_outputs: numOutputs,
      num_inference_steps: steps,
      scale,
    },
  };
};
