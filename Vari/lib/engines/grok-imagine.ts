import { buildPrompt } from "../prompts";
import type { EngineBuilder } from "./types";

export const buildGrokImaginePayload: EngineBuilder = (ctx) => {
  const { prompt } = buildPrompt(ctx.distance);

  return {
    _model_id: "xai/grok-imagine-image/edit",
    prompt,
    image_urls: [ctx.sourceUrl],
    num_images: Math.min(ctx.count, 4),
    resolution: "2k",
    output_format: "png",
  };
};
