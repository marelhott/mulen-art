import { buildPrompt } from "../prompts";
import type { EngineBuilder } from "./types";

export const buildZImagePayload: EngineBuilder = (ctx) => {
  const { prompt, negativePrompt } = buildPrompt(ctx.distance);
  const creativity =
    typeof ctx.zImageCreativity === "number"
      ? ctx.zImageCreativity
      : ctx.distance === "locked"
        ? 0.36
        : ctx.distance === "sibling"
          ? 0.5
          : ctx.distance === "looser"
            ? 0.66
            : 0.8;

  return {
    _model_id: "fal-ai/z-image/turbo/image-to-image",
    image_url: ctx.sourceUrl,
    prompt,
    negative_prompt: negativePrompt,
    num_images: Math.min(ctx.count, 4),
    image_size: "auto",
    num_inference_steps:
      ctx.distance === "locked"
        ? 8
        : ctx.distance === "sibling"
          ? 7
          : ctx.distance === "looser"
            ? 6
            : 5,
    strength: creativity,
    acceleration: ctx.distance === "locked" ? "none" : "regular",
    enable_prompt_expansion: false,
    enable_safety_checker: false,
    output_format: "png",
  };
};
