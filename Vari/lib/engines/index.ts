import type { Engine } from "../engines";
import type { EngineBuilder } from "./types";
import { buildSdxlArtisticPayload } from "./sdxl-artistic";
import { buildStablePayload } from "./stable";
import { buildSdVariationPayload } from "./sd-variation";
import { buildUnclipPayload } from "./unclip";
import { buildComfyUnclipPayload } from "./comfy-unclip";
import { buildIpAdapterSdxlPayload } from "./ip-adapter-sdxl";
import { buildFofrAnyComfyuiWorkflowPayload } from "./fofr-any-comfyui-workflow";
import { buildChigozienriIpAdapterSdxlPayload } from "./chigozienri-ip-adapter-sdxl";
import { buildZImagePayload } from "./z-image";
import { buildGrokImaginePayload } from "./grok-imagine";

const buildVisionRemixPayload: EngineBuilder = () => {
  throw new Error("Vision Remix se zpracovává přímo v API route.");
};
const buildGptImage2Payload: EngineBuilder = () => {
  throw new Error("GPT Image 2 se zpracovává přímo v API route.");
};
const buildGemini3ProPayload: EngineBuilder = () => {
  throw new Error("Gemini 3 Pro se zpracovává přímo v API route.");
};

export const ENGINE_BUILDERS: Record<Engine, EngineBuilder> = {
  "gpt-image-2": buildGptImage2Payload,
  "gemini-3-pro": buildGemini3ProPayload,
  "z-image": buildZImagePayload,
  "grok-imagine": buildGrokImaginePayload,
  "sd-variation": buildSdVariationPayload,
  "vision-remix": buildVisionRemixPayload,
  "ip-adapter-sdxl": buildIpAdapterSdxlPayload,
  "chigozienri-ip-adapter-sdxl": buildChigozienriIpAdapterSdxlPayload,
  unclip: buildUnclipPayload,
  "comfy-unclip": buildComfyUnclipPayload,
  "sdxl-artistic": buildSdxlArtisticPayload,
  stable: buildStablePayload,
  "fofr-any-comfyui-workflow": buildFofrAnyComfyuiWorkflowPayload,
};

export type { EngineBuilder, EngineContext, EnginePayload } from "./types";
