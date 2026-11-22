import { fal } from "@fal-ai/client";

// Configure once at module load instead of on every call.
if (process.env.FAL_KEY) {
  fal.config({ credentials: process.env.FAL_KEY });
}

export type FalPayload = Record<string, unknown> & {
  _model_id: string;
  _repeat?: number;
};

export type ExtractedImage = { url: string };

function bufferToDataUri(buffer: Buffer, mimeType: string) {
  return `data:${mimeType};base64,${buffer.toString("base64")}`;
}

// Upload a buffer to fal storage and return a public URL. Used to avoid
// base64-encoding the full image into every provider request.
export async function uploadBufferToFal(buffer: Buffer, mimeType = "image/png"): Promise<string> {
  if (!process.env.FAL_KEY) {
    return bufferToDataUri(buffer, mimeType);
  }

  try {
    const blob = new Blob([new Uint8Array(buffer)], { type: mimeType });
    // @fal-ai/client exposes storage.upload(File|Blob) → URL.
    const url = await fal.storage.upload(blob as unknown as File);
    return url;
  } catch {
    return bufferToDataUri(buffer, mimeType);
  }
}

function normalizeImageCandidate(candidate: unknown): ExtractedImage | null {
  if (typeof candidate === "string") return { url: candidate };
  if (candidate && typeof candidate === "object") {
    const value = candidate as Record<string, unknown>;
    if (typeof value.url === "string") return { url: value.url };
    if (typeof value.image_url === "string") return { url: value.image_url };
  }
  return null;
}

export function extractFalImages(result: Record<string, unknown>): ExtractedImage[] {
  const buckets = [
    result.images,
    result.image,
    result.image_url,
    (result.data as Record<string, unknown> | undefined)?.images,
    (result.data as Record<string, unknown> | undefined)?.image,
    (result.data as Record<string, unknown> | undefined)?.image_url,
    (result.output as Record<string, unknown> | undefined)?.images,
    (result.output as Record<string, unknown> | undefined)?.image,
    (result.output as Record<string, unknown> | undefined)?.image_url,
  ];
  return buckets.flatMap((bucket) => {
    if (Array.isArray(bucket)) {
      return bucket.map(normalizeImageCandidate).filter(Boolean) as ExtractedImage[];
    }
    const normalized = normalizeImageCandidate(bucket);
    return normalized ? [normalized] : [];
  });
}

export type FalRunResult = { images: ExtractedImage[]; raw: Record<string, unknown> };

export async function runFalPayload(
  payload: FalPayload,
  options: { timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<FalRunResult> {
  const { timeoutMs = 1000 * 60 * 5, signal } = options;
  const modelId = payload._model_id;
  const repeat = Math.max(1, Number(payload._repeat ?? 1));

  const input: Record<string, unknown> = { ...payload };
  delete input._model_id;
  delete input._repeat;

  const images: ExtractedImage[] = [];
  let lastResult: Record<string, unknown> = {};

  for (let i = 0; i < repeat; i += 1) {
    if (signal?.aborted) throw new Error("Zrušeno uživatelem.");
    const result = (await fal.subscribe(modelId, {
      input,
      timeout: timeoutMs,
      mode: "polling",
      abortSignal: signal,
    })) as Record<string, unknown>;
    lastResult = result;
    images.push(...extractFalImages(result));
  }

  return { images, raw: lastResult };
}
