import sharp from "sharp";

export type AspectRatioLabel =
  | "1:1"
  | "2:3"
  | "3:2"
  | "3:4"
  | "4:3"
  | "4:5"
  | "5:4"
  | "9:16"
  | "16:9";

export type ImageInfo = {
  width: number;
  height: number;
  aspectRatio: AspectRatioLabel;
};

export const SUPPORTED_RATIOS: Array<{ value: AspectRatioLabel; ratio: number }> = [
  { value: "1:1", ratio: 1 },
  { value: "2:3", ratio: 2 / 3 },
  { value: "3:2", ratio: 3 / 2 },
  { value: "3:4", ratio: 3 / 4 },
  { value: "4:3", ratio: 4 / 3 },
  { value: "4:5", ratio: 4 / 5 },
  { value: "5:4", ratio: 5 / 4 },
  { value: "9:16", ratio: 9 / 16 },
  { value: "16:9", ratio: 16 / 9 },
];

export async function getImageInfo(buffer: Buffer): Promise<ImageInfo> {
  const metadata = await sharp(buffer).metadata();
  const width = metadata.width || 1024;
  const height = metadata.height || 1024;
  const sourceRatio = width / height;
  const nearest = SUPPORTED_RATIOS.reduce((best, candidate) => {
    return Math.abs(candidate.ratio - sourceRatio) < Math.abs(best.ratio - sourceRatio)
      ? candidate
      : best;
  }, SUPPORTED_RATIOS[0]);
  return { width, height, aspectRatio: nearest.value };
}

// Pick the fal image_size preset that most closely matches the source
// orientation. fal endpoints support: "square", "landscape_4_3",
// "landscape_16_9", "portrait_4_3", "portrait_16_9".
export function falImageSize(info: ImageInfo): string {
  const ratio = info.width / info.height;
  if (Math.abs(ratio - 1) < 0.05) return "square";
  if (ratio >= 1.6) return "landscape_16_9";
  if (ratio <= 1 / 1.6) return "portrait_16_9";
  return ratio >= 1 ? "landscape_4_3" : "portrait_4_3";
}

// Nearest SDXL-friendly width/height on a 64-px grid, preserving aspect.
export function snappedDimensions(info: ImageInfo, longSide = 1024): { width: number; height: number } {
  const ratio = info.width / info.height;
  if (ratio >= 1) {
    const w = longSide;
    const h = Math.max(512, Math.round((longSide / ratio) / 64) * 64);
    return { width: w, height: h };
  }
  const h = longSide;
  const w = Math.max(512, Math.round((longSide * ratio) / 64) * 64);
  return { width: w, height: h };
}
