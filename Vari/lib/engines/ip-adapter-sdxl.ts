import type { EngineBuilder } from "./types";

const IP_ADAPTER_SDXL_VERSION =
  "904dc004af1dba5c9b13fc9e41635aeb2f9a177896a396ab3393f3f6493dbdd4";

export const buildIpAdapterSdxlPayload: EngineBuilder = (ctx) => {
  const numOutputs = Math.min(ctx.count, 4);
  const scale =
    typeof ctx.ipAdapterScale === "number"
      ? ctx.ipAdapterScale
      : ctx.distance === "locked"
        ? 0.82
        : ctx.distance === "sibling"
          ? 0.66
          : ctx.distance === "looser"
            ? 0.52
            : 0.4;

  const steps =
    typeof ctx.ipAdapterSteps === "number"
      ? Math.round(ctx.ipAdapterSteps)
      : ctx.distance === "locked"
        ? 55
        : ctx.distance === "sibling"
          ? 48
          : ctx.distance === "looser"
            ? 44
            : 40;

  return {
    _provider: "replicate",
    version: IP_ADAPTER_SDXL_VERSION,
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
