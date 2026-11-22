import { snappedDimensions } from "../image-info";
import type { ImageInfo } from "../image-info";
import type { Distance } from "../engines";
import { buildPrompt } from "../prompts";
import type { EngineBuilder } from "./types";

const COMFY_UNCLIP_VERSION =
  "16d0a881fbfc066f0471a3519a347db456fe8cbcbd53abb435a50a74efaeb427";

// NOTE: This still targets SD 1.5 + IPAdapter. The comfy path is kept for speed
// and controllability, but for a higher-detail image-first path prefer the
// dedicated SDXL IP-Adapter engine. This is the only engine that explicitly
// uses a square IPAdapter reference image.
const COMFY_CHECKPOINT = "v1-5-pruned-emaonly.ckpt";

function volatility(distance: Distance) {
  return {
    locked: { noise: 0.21, strength: 0.86, cfg: 3.2, steps: 45 },
    sibling: { noise: 0.21, strength: 0.86, cfg: 2.8, steps: 42 },
    looser: { noise: 0.21, strength: 0.86, cfg: 2.5, steps: 40 },
    "new-frame": { noise: 0.21, strength: 0.86, cfg: 2.3, steps: 40 },
  }[distance];
}

export function buildComfyUnclipWorkflow({
  inputFileName,
  count,
  imageInfo,
  distance,
  comfyNoise,
  comfyStrength,
}: {
  inputFileName: string;
  count: number;
  imageInfo: ImageInfo;
  distance: Distance;
  comfyNoise?: number;
  comfyStrength?: number;
}) {
  const { prompt, negativePrompt } = buildPrompt(distance);
  // SD 1.5 is trained on 512 but 1024 long-side works cleanly with the SDXL
  // IPAdapter pipe and gives much more detail than 768.
  const { width, height } = snappedDimensions(imageInfo, 1024);
  const v = volatility(distance);
  const noise = typeof comfyNoise === "number" ? Math.max(0, Math.min(0.35, comfyNoise)) : v.noise;
  const strength =
    typeof comfyStrength === "number" ? Math.max(0.35, Math.min(1, comfyStrength)) : v.strength;
  const ipWeight = Math.max(0.35, Math.min(0.95, strength - noise * 0.35));

  return {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: { ckpt_name: COMFY_CHECKPOINT },
    },
    "2": { class_type: "LoadImage", inputs: { image: inputFileName } },
    "3": {
      class_type: "IPAdapterUnifiedLoader",
      inputs: { model: ["1", 0], preset: "PLUS (high strength)" },
    },
    "4": {
      class_type: "IPAdapter",
      inputs: {
        model: ["3", 0],
        ipadapter: ["3", 1],
        image: ["2", 0],
        weight: ipWeight,
        start_at: 0,
        end_at: 1,
        weight_type: "standard",
      },
    },
    "5": {
      class_type: "CLIPTextEncode",
      inputs: { clip: ["1", 1], text: prompt },
    },
    "6": {
      class_type: "CLIPTextEncode",
      inputs: { clip: ["1", 1], text: negativePrompt },
    },
    "7": {
      class_type: "EmptyLatentImage",
      inputs: { width, height, batch_size: count },
    },
    "8": {
      class_type: "KSampler",
      inputs: {
        seed: Math.floor(Math.random() * 1_000_000_000_000),
        steps: v.steps,
        cfg: v.cfg,
        sampler_name: "dpmpp_2m",
        scheduler: "karras",
        denoise: 1,
        model: ["4", 0],
        positive: ["5", 0],
        negative: ["6", 0],
        latent_image: ["7", 0],
      },
    },
    "9": {
      class_type: "VAEDecode",
      inputs: { samples: ["8", 0], vae: ["1", 2] },
    },
    "10": {
      class_type: "SaveImage",
      inputs: { filename_prefix: "variants-comfy-unclip", images: ["9", 0] },
    },
  };
}

export const buildComfyUnclipPayload: EngineBuilder = (ctx) => {
  return {
    _provider: "replicate",
    version: COMFY_UNCLIP_VERSION,
    input: {
      workflow_json: JSON.stringify(
        buildComfyUnclipWorkflow({
          inputFileName: "input.png",
          count: ctx.count,
          imageInfo: ctx.imageInfo,
          distance: ctx.distance,
          comfyNoise: ctx.comfyNoise,
          comfyStrength: ctx.comfyStrength,
        }),
      ),
      input_file: ctx.comfyReferenceUrl ?? ctx.sourceUrl,
      return_temp_files: false,
      output_format: "png",
      output_quality: 95,
      randomise_seeds: false,
    },
  };
};
