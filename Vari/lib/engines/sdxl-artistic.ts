import { buildPrompt } from "../prompts";
import { snappedDimensions } from "../image-info";
import type { EngineBuilder } from "./types";

// High-detail SDXL i2i. Custom width/height on a 64-px grid (1280 long side)
// keeps aspect ratio honest AND pushes resolution above the default preset
// (landscape_4_3 is only 1024×768). fal's fast-sdxl accepts { width, height }.
export const buildSdxlArtisticPayload: EngineBuilder = (ctx) => {
  const { prompt, negativePrompt } = buildPrompt(ctx.distance);
  const { width, height } = snappedDimensions(ctx.imageInfo, 1280);
  const guidance =
    typeof ctx.sdxlGuidance === "number"
      ? ctx.sdxlGuidance
      : ctx.distance === "locked"
        ? 3.6
        : ctx.distance === "sibling"
          ? 3.2
          : ctx.distance === "looser"
            ? 2.9
            : 2.6;
  const steps =
    typeof ctx.sdxlSteps === "number"
      ? Math.round(ctx.sdxlSteps)
      : ctx.distance === "locked"
        ? 40
        : ctx.distance === "sibling"
          ? 36
          : ctx.distance === "looser"
            ? 32
            : 28;
  const strength =
    typeof ctx.sdxlStrength === "number"
      ? ctx.sdxlStrength
      : ctx.distance === "locked"
        ? 0.42
        : ctx.distance === "sibling"
          ? 0.5
          : ctx.distance === "looser"
            ? 0.58
            : 0.66;
  return {
    _model_id: "fal-ai/fast-sdxl/image-to-image",
    image_url: ctx.sourceUrl,
    prompt,
    negative_prompt: negativePrompt,
    num_images: ctx.count,
    image_size: { width, height },
    enable_safety_checker: false,
    expand_prompt: false,
    guidance_scale: guidance,
    num_inference_steps: steps,
    strength,
    format: "png",
  };
};
