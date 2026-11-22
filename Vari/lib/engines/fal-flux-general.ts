import { buildPrompt } from "../prompts";
import { snappedDimensions } from "../image-info";
import type { EngineBuilder } from "./types";

export const buildFalFluxGeneralPayload: EngineBuilder = (ctx) => {
  const numImages = Math.min(ctx.count, 4);
  const { prompt, negativePrompt } = buildPrompt(ctx.distance);
  const { width, height } = snappedDimensions(ctx.imageInfo, 1440);

  const referenceStrength =
    ctx.distance === "locked"
      ? 0.82
      : ctx.distance === "sibling"
        ? 0.72
        : ctx.distance === "looser"
          ? 0.62
          : 0.52;

  const controllerGuidanceReverse =
    ctx.distance === "locked"
      ? 0.88
      : ctx.distance === "sibling"
        ? 0.8
        : ctx.distance === "looser"
          ? 0.72
          : 0.66;

  return {
    _model_id: "fal-ai/flux-general/rf-inversion",
    image_url: ctx.sourceUrl,
    prompt,
    negative_prompt: negativePrompt,
    num_images: numImages,
    image_size: { width, height },
    num_inference_steps:
      ctx.distance === "locked"
        ? 40
        : ctx.distance === "sibling"
          ? 36
          : ctx.distance === "looser"
            ? 32
            : 28,
    guidance_scale:
      ctx.distance === "locked"
        ? 3.4
        : ctx.distance === "sibling"
          ? 3.1
          : ctx.distance === "looser"
            ? 2.8
            : 2.5,
    use_cfg_zero: false,
    reference_image_url: ctx.sourceUrl,
    reference_strength: referenceStrength,
    reference_end: 0.92,
    controller_guidance_forward:
      ctx.distance === "locked"
        ? 0.68
        : ctx.distance === "sibling"
          ? 0.62
          : ctx.distance === "looser"
            ? 0.56
            : 0.5,
    controller_guidance_reverse: controllerGuidanceReverse,
    reverse_guidance_end:
      ctx.distance === "locked"
        ? 10
        : ctx.distance === "sibling"
          ? 8
          : ctx.distance === "looser"
            ? 6
            : 5,
    reverse_guidance_schedule:
      ctx.distance === "locked" || ctx.distance === "sibling"
        ? "constant"
        : "linear_decrease",
    scheduler: "euler",
    nag_scale:
      ctx.distance === "locked"
        ? 2.6
        : ctx.distance === "sibling"
          ? 2.9
          : ctx.distance === "looser"
            ? 3.1
            : 3.3,
    enable_safety_checker: false,
    output_format: "png",
  };
};
