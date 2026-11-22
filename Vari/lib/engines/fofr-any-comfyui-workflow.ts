import { snappedDimensions } from "../image-info";
import { buildPrompt } from "../prompts";
import type { Distance } from "../engines";
import type { ImageInfo } from "../image-info";
import type { EngineBuilder } from "./types";

const FOFR_ANY_COMFYUI_WORKFLOW_VERSION =
  "7896cf903d3fff4ac5edf2d46918a7a9e51ed7d6d4e0192ab1264587ada22692";

const SDXL_CHECKPOINT = "sd_xl_base_1.0.safetensors";

function workflowVolatility(distance: Distance) {
  return {
    locked: { cfg: 3.6, steps: 54, ipWeight: 0.86 },
    sibling: { cfg: 3.2, steps: 48, ipWeight: 0.76 },
    looser: { cfg: 2.9, steps: 44, ipWeight: 0.64 },
    "new-frame": { cfg: 2.6, steps: 40, ipWeight: 0.52 },
  }[distance];
}

function buildWorkflow({
  inputFileName,
  count,
  imageInfo,
  distance,
  cfgOverride,
  stepsOverride,
  ipWeightOverride,
}: {
  inputFileName: string;
  count: number;
  imageInfo: ImageInfo;
  distance: Distance;
  cfgOverride?: number;
  stepsOverride?: number;
  ipWeightOverride?: number;
}) {
  const { prompt, negativePrompt } = buildPrompt(distance);
  const { width, height } = snappedDimensions(imageInfo, 1280);
  const tuned = workflowVolatility(distance);
  const cfg = typeof cfgOverride === "number" ? cfgOverride : tuned.cfg;
  const steps = typeof stepsOverride === "number" ? Math.round(stepsOverride) : tuned.steps;
  const ipWeight = typeof ipWeightOverride === "number" ? ipWeightOverride : tuned.ipWeight;

  return {
    "1": {
      class_type: "CheckpointLoaderSimple",
      inputs: { ckpt_name: SDXL_CHECKPOINT },
    },
    "2": {
      class_type: "LoadImage",
      inputs: { image: inputFileName },
    },
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
        steps,
        cfg,
        sampler_name: "dpmpp_2m_sde",
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
      inputs: { filename_prefix: "variants-fofr-sdxl-ipadapter", images: ["9", 0] },
    },
  };
}

export const buildFofrAnyComfyuiWorkflowPayload: EngineBuilder = (ctx) => {
  return {
    _provider: "replicate",
    version: FOFR_ANY_COMFYUI_WORKFLOW_VERSION,
    input: {
      workflow_json: JSON.stringify(
        buildWorkflow({
          inputFileName: "input.png",
          count: ctx.count,
          imageInfo: ctx.imageInfo,
          distance: ctx.distance,
          cfgOverride: ctx.fofrCfg,
          stepsOverride: ctx.fofrSteps,
          ipWeightOverride: ctx.fofrIpWeight,
        }),
      ),
      input_file: ctx.sourceUrl,
      return_temp_files: false,
      randomise_seeds: false,
    },
  };
};
