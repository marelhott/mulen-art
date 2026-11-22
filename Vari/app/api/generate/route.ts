import { NextRequest, NextResponse } from "next/server";
import sharp from "sharp";
import { saveBufferImage, saveRemoteImage } from "@/lib/storage";
import { getImageInfo } from "@/lib/image-info";
import {
  DEFAULT_EXPECTED_COUNT,
  isDistance,
  isEngine,
  type Distance,
  type Engine,
} from "@/lib/engines";
import { ENGINE_BUILDERS } from "@/lib/engines/index";
import type { EngineContext, EnginePayload } from "@/lib/engines/types";
import { snappedDimensions } from "@/lib/image-info";
import { uploadBufferToFal, runFalPayload } from "@/lib/providers/fal";
import { editWithGemini3Pro } from "@/lib/providers/gemini";
import { analyzeImageForVariant, analyzeVisionRemix, buildGptImage2Prompt, editWithGptImage2 } from "@/lib/providers/openai";
import {
  createReplicatePrediction,
  type ReplicatePayload,
} from "@/lib/providers/replicate";

function isReplicate(payload: EnginePayload): payload is ReplicatePayload {
  return (payload as ReplicatePayload)._provider === "replicate";
}

// Build a square IP-Adapter reference for the Comfy engine only. Other
// engines get the image as-is — no aspect-ratio transformation.
async function buildComfySquareReference(buffer: Buffer) {
  const metadata = await sharp(buffer).metadata();
  const square = Math.max(metadata.width || 1024, metadata.height || 1024);
  const bg = await sharp(buffer)
    .resize(square, square, { fit: "cover" })
    .blur(18)
    .modulate({ saturation: 0.92, brightness: 0.9 })
    .png()
    .toBuffer();
  const fg = await sharp(buffer)
    .removeAlpha()
    .resize(square, square, { fit: "contain", background: { r: 12, g: 12, b: 12, alpha: 1 } })
    .png()
    .toBuffer();
  return sharp(bg).composite([{ input: fg, blend: "over" }]).png().toBuffer();
}

async function runFalPayloadWithRetry(
  payload: Parameters<typeof runFalPayload>[0],
  options: Parameters<typeof runFalPayload>[1],
  retries = 2,
) {
  let lastError: unknown;
  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      return await runFalPayload(payload, options);
    } catch (error) {
      lastError = error;
      if (attempt === retries - 1) break;
      await new Promise((resolve) => setTimeout(resolve, 900 * (attempt + 1)));
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Fal request failed.");
}

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const imageFile = formData.get("image");
    const rawDistance = String(formData.get("distance") || "sibling");
    const rawEngine = String(formData.get("engine") || "sd-variation");
    const count = Math.max(1, Math.min(DEFAULT_EXPECTED_COUNT, Number(formData.get("count") || 4)));
    const comfyNoise = Number(formData.get("comfyNoise"));
    const comfyStrength = Number(formData.get("comfyStrength"));
    const ipAdapterScale = Number(formData.get("ipAdapterScale"));
    const ipAdapterSteps = Number(formData.get("ipAdapterSteps"));
    const chigoScale = Number(formData.get("chigoScale"));
    const chigoSteps = Number(formData.get("chigoSteps"));
    const sdxlGuidance = Number(formData.get("sdxlGuidance"));
    const sdxlStrength = Number(formData.get("sdxlStrength"));
    const sdxlSteps = Number(formData.get("sdxlSteps"));
    const stableGuidance = Number(formData.get("stableGuidance"));
    const stableStrength = Number(formData.get("stableStrength"));
    const stableSteps = Number(formData.get("stableSteps"));
    const sdVariationGuidance = Number(formData.get("sdVariationGuidance"));
    const sdVariationSteps = Number(formData.get("sdVariationSteps"));
    const fofrCfg = Number(formData.get("fofrCfg"));
    const fofrSteps = Number(formData.get("fofrSteps"));
    const fofrIpWeight = Number(formData.get("fofrIpWeight"));
    const zImageCreativity = Number(formData.get("zImageCreativity"));

    if (!(imageFile instanceof File)) {
      return NextResponse.json({ error: "Nebyl nahrán obrázek." }, { status: 400 });
    }

    const distance: Distance = isDistance(rawDistance) ? rawDistance : "sibling";
    const engine: Engine = isEngine(rawEngine) ? rawEngine : "sd-variation";

    const original = Buffer.from(await imageFile.arrayBuffer());
    const normalized = await sharp(original).removeAlpha().png().toBuffer();
    const imageInfo = await getImageInfo(normalized);

    // Upload once, reuse URL across all providers.
    const sourceUrl = await uploadBufferToFal(normalized, "image/png");

    if (engine === "gpt-image-2") {
      const analysis = await analyzeImageForVariant(sourceUrl);
      const prompt = buildGptImage2Prompt(distance, analysis);
      const size =
        imageInfo.width === imageInfo.height
          ? "1024x1024"
          : imageInfo.width > imageInfo.height
            ? "1536x1024"
            : "1024x1536";
      const outputBuffers = await editWithGptImage2(
        normalized,
        prompt,
        Math.max(1, Math.min(4, count)),
        size,
      );
      if (!outputBuffers.length) {
        return NextResponse.json({ error: "GPT Image 2 nevrátil žádné obrázky." }, { status: 502 });
      }
      const localJobId = `${Date.now()}-${engine}`;
      const saved = await Promise.all(
        outputBuffers.map((buffer, index) => saveBufferImage(buffer, localJobId, index, "image/png")),
      );
      return NextResponse.json({ images: saved });
    }

    if (engine === "gemini-3-pro") {
      const analysis = await analyzeImageForVariant(sourceUrl);
      const prompt = buildGptImage2Prompt(distance, analysis);
      const outputBuffers = await editWithGemini3Pro(
        normalized,
        prompt,
        Math.max(1, Math.min(4, count)),
        imageInfo.width,
        imageInfo.height,
      );
      if (!outputBuffers.length) {
        return NextResponse.json({ error: "Gemini 3 Pro nevrátil žádné obrázky." }, { status: 502 });
      }
      const localJobId = `${Date.now()}-${engine}`;
      const saved = await Promise.all(
        outputBuffers.map((buffer, index) => saveBufferImage(buffer, localJobId, index, "image/png")),
      );
      return NextResponse.json({ images: saved });
    }

    if (engine === "vision-remix") {
      const { prompt } = await analyzeVisionRemix(sourceUrl, distance);
      const { width, height } = snappedDimensions(imageInfo, 1344);
      const { images } = await runFalPayloadWithRetry(
        {
          _model_id: "fal-ai/fast-sdxl/image-to-image",
          image_url: sourceUrl,
          prompt,
          negative_prompt:
            "exact duplicate, same framing, same crop, same composition, polished stock photo, glossy render, generic concept art, vectorized simplification, poster design",
          num_images: Math.max(1, Math.min(4, count)),
          image_size: { width, height },
          num_inference_steps:
            distance === "locked"
              ? 40
              : distance === "sibling"
                ? 36
                : distance === "looser"
                  ? 32
                  : 28,
          guidance_scale:
            distance === "locked"
              ? 3.6
              : distance === "sibling"
                ? 3.2
                : distance === "looser"
                  ? 2.9
                  : 2.6,
          strength:
            distance === "locked"
              ? 0.42
              : distance === "sibling"
                ? 0.52
                : distance === "looser"
                  ? 0.64
                  : 0.76,
          expand_prompt: false,
          enable_safety_checker: false,
          format: "png",
        },
        { signal: req.signal },
      );
      const urls = images.map((img) => img.url).filter(Boolean);
      if (!urls.length) {
        return NextResponse.json({ error: "Vision Remix nevrátil žádné obrázky." }, { status: 502 });
      }
      const localJobId = `${Date.now()}-${engine}`;
      const saved = await Promise.all(
        urls.map((url, index) => saveRemoteImage(url, localJobId, index)),
      );
      return NextResponse.json({ images: saved });
    }

    const comfyReferenceUrl =
      engine === "comfy-unclip"
        ? await uploadBufferToFal(await buildComfySquareReference(normalized), "image/png")
        : undefined;

    const ctx: EngineContext = {
      sourceUrl,
      comfyReferenceUrl,
      imageInfo,
      distance,
      count,
      comfyNoise: Number.isFinite(comfyNoise) ? comfyNoise : undefined,
      comfyStrength: Number.isFinite(comfyStrength) ? comfyStrength : undefined,
      ipAdapterScale: Number.isFinite(ipAdapterScale) ? ipAdapterScale : undefined,
      ipAdapterSteps: Number.isFinite(ipAdapterSteps) ? ipAdapterSteps : undefined,
      chigoScale: Number.isFinite(chigoScale) ? chigoScale : undefined,
      chigoSteps: Number.isFinite(chigoSteps) ? chigoSteps : undefined,
      sdxlGuidance: Number.isFinite(sdxlGuidance) ? sdxlGuidance : undefined,
      sdxlStrength: Number.isFinite(sdxlStrength) ? sdxlStrength : undefined,
      sdxlSteps: Number.isFinite(sdxlSteps) ? sdxlSteps : undefined,
      stableGuidance: Number.isFinite(stableGuidance) ? stableGuidance : undefined,
      stableStrength: Number.isFinite(stableStrength) ? stableStrength : undefined,
      stableSteps: Number.isFinite(stableSteps) ? stableSteps : undefined,
      sdVariationGuidance: Number.isFinite(sdVariationGuidance) ? sdVariationGuidance : undefined,
      sdVariationSteps: Number.isFinite(sdVariationSteps) ? sdVariationSteps : undefined,
      fofrCfg: Number.isFinite(fofrCfg) ? fofrCfg : undefined,
      fofrSteps: Number.isFinite(fofrSteps) ? fofrSteps : undefined,
      fofrIpWeight: Number.isFinite(fofrIpWeight) ? fofrIpWeight : undefined,
      zImageCreativity: Number.isFinite(zImageCreativity) ? zImageCreativity : undefined,
    };

    const payload = ENGINE_BUILDERS[engine](ctx);

    if (isReplicate(payload)) {
      const repeat = Math.max(1, Number(payload._repeat ?? 1));
      const predictions = await Promise.all(
        Array.from({ length: repeat }, () => createReplicatePrediction(payload, { signal: req.signal })),
      );
      return NextResponse.json({
        jobId: predictions[0]?.id ?? null,
        jobIds: predictions.map((prediction) => prediction.id),
        provider: "replicate",
        status: predictions[0]?.status || "starting",
      });
    }

    const { images } = await runFalPayload(payload, { signal: req.signal });
    const urls = images.map((img) => img.url).filter(Boolean);

    if (!urls.length) {
      return NextResponse.json({ error: "Model nevrátil žádné obrázky." }, { status: 502 });
    }

    const localJobId = `${Date.now()}-${engine}`;
    const saved = await Promise.all(
      urls.map((url, index) => saveRemoteImage(url, localJobId, index)),
    );

    return NextResponse.json({ images: saved });
  } catch (error) {
    if (error && typeof error === "object") {
      const maybe = error as {
        message?: string;
        status?: number;
        body?: unknown;
        requestId?: string;
      };
      console.error(
        "Generate route error",
        JSON.stringify(
          {
            message: maybe.message,
            status: maybe.status,
            requestId: maybe.requestId,
            body: maybe.body,
          },
          null,
          2,
        ),
      );
    } else {
      console.error(error);
    }
    const message = error instanceof Error ? error.message : "Generování selhalo.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export const maxDuration = 300;
