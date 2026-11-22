import type { Distance } from "../engines";
import type { ImageInfo } from "../image-info";
import type { FalPayload } from "../providers/fal";
import type { ReplicatePayload } from "../providers/replicate";

export type EnginePayload = FalPayload | ReplicatePayload;

export type EngineContext = {
  // Public URL to the normalized RGB PNG of the source image.
  sourceUrl: string;
  // Public URL to the square IPAdapter reference (only comfy-unclip uses it).
  comfyReferenceUrl?: string;
  // Info about the source dimensions + nearest aspect ratio preset.
  imageInfo: ImageInfo;
  distance: Distance;
  count: number;
  comfyNoise?: number;
  comfyStrength?: number;
  ipAdapterScale?: number;
  ipAdapterSteps?: number;
  chigoScale?: number;
  chigoSteps?: number;
  sdxlGuidance?: number;
  sdxlStrength?: number;
  sdxlSteps?: number;
  stableGuidance?: number;
  stableStrength?: number;
  stableSteps?: number;
  sdVariationGuidance?: number;
  sdVariationSteps?: number;
  fofrCfg?: number;
  fofrSteps?: number;
  fofrIpWeight?: number;
  zImageCreativity?: number;
};

export type EngineBuilder = (ctx: EngineContext) => EnginePayload;
