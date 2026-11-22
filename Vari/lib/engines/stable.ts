import { buildPrompt } from "../prompts";
import type { EngineBuilder } from "./types";

export const buildStablePayload: EngineBuilder = (ctx) => {
  const { prompt, negativePrompt } = buildPrompt(ctx.distance);
  return {
    _model_id: "fal-ai/stable-diffusion-v3-medium/image-to-image",
    image_url: ctx.sourceUrl,
    prompt,
    negative_prompt: negativePrompt,
    num_images: ctx.count,
    image_size:
      ctx.imageInfo.aspectRatio === "1:1"
        ? "square"
        : ctx.imageInfo.width >= ctx.imageInfo.height
          ? "landscape_4_3"
          : "portrait_4_3",
    num_inference_steps: typeof ctx.stableSteps === "number" ? Math.round(ctx.stableSteps) : 30,
    guidance_scale:
      typeof ctx.stableGuidance === "number"
        ? ctx.stableGuidance
        : ctx.distance === "new-frame"
          ? 3.2
          : 3.8,
    strength:
      typeof ctx.stableStrength === "number"
        ? ctx.stableStrength
        : ctx.distance === "new-frame"
          ? 0.92
          : ctx.distance === "looser"
            ? 0.82
            : 0.68,
    enable_safety_checker: false,
  };
};
