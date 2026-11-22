import { buildPrompt } from "../prompts";
import { snappedDimensions } from "../image-info";
import type { EngineBuilder } from "./types";

const DREAM_O_VERSION =
  "8f8d84ebe012e94a126b21c953b8dc33be86e4cf92b133b144bda94aa84e616b";

export const buildDreamOPayload: EngineBuilder = (ctx) => {
  const { prompt, negativePrompt } = buildPrompt(ctx.distance);
  const base = snappedDimensions(ctx.imageInfo, 1024);
  const width = Math.max(768, base.width);
  const height = Math.max(768, base.height);

  const referenceDominantPrompt =
    ctx.distance === "locked" || ctx.distance === "sibling" ? "" : prompt;

  return {
    _provider: "replicate",
    version: DREAM_O_VERSION,
    _repeat: Math.max(1, ctx.count),
    input: {
      prompt: referenceDominantPrompt,
      ref_image1: ctx.sourceUrl,
      ref_task1: "ip",
      width,
      height,
      num_steps:
        ctx.distance === "locked"
          ? 24
          : ctx.distance === "sibling"
            ? 20
            : ctx.distance === "looser"
              ? 16
              : 14,
      guidance:
        ctx.distance === "locked"
          ? 2.4
          : ctx.distance === "sibling"
            ? 2.8
            : ctx.distance === "looser"
              ? 3.2
              : 3.6,
      ref_res:
        ctx.distance === "locked"
          ? 1024
          : ctx.distance === "sibling"
            ? 896
            : 768,
      neg_prompt: negativePrompt,
      neg_guidance:
        ctx.distance === "locked"
          ? 2.2
          : ctx.distance === "sibling"
            ? 2.6
            : 3,
      true_cfg: ctx.distance === "locked" ? 1.2 : 1,
      cfg_start_step: 0,
      cfg_end_step: 0,
      first_step_guidance: 0,
      output_format: "png",
      output_quality: 95,
    },
  };
};
