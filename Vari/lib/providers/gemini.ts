const GEMINI_API = "https://generativelanguage.googleapis.com/v1beta";
const GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview";

function key(): string {
  const token = process.env.GEMINI_API_KEY;
  if (!token) {
    throw new Error("Chybí GEMINI_API_KEY v prostředí. Gemini 3 Pro bez něj nepoběží.");
  }
  return token;
}

function aspectRatioFor(width: number, height: number): string {
  if (width === height) return "1:1";
  if (width > height) {
    const ratio = width / height;
    if (ratio >= 1.85) return "21:9";
    if (ratio >= 1.55) return "16:9";
    if (ratio >= 1.22) return "4:3";
    return "3:2";
  }

  const ratio = height / width;
  if (ratio >= 1.85) return "9:16";
  if (ratio >= 1.45) return "2:3";
  if (ratio >= 1.28) return "3:4";
  return "4:5";
}

function extractInlineImageBuffers(data: Record<string, unknown>): Buffer[] {
  const candidates = Array.isArray(data.candidates)
    ? (data.candidates as Array<Record<string, unknown>>)
    : [];

  const buffers: Buffer[] = [];
  for (const candidate of candidates) {
    const content =
      candidate && typeof candidate === "object" && candidate.content && typeof candidate.content === "object"
        ? (candidate.content as Record<string, unknown>)
        : null;
    const parts = Array.isArray(content?.parts) ? (content?.parts as Array<Record<string, unknown>>) : [];

    for (const part of parts) {
      const inlineData =
        part && typeof part === "object" && part.inlineData && typeof part.inlineData === "object"
          ? (part.inlineData as Record<string, unknown>)
          : null;
      const b64 = inlineData?.data;
      if (typeof b64 === "string" && b64.length > 0) {
        buffers.push(Buffer.from(b64, "base64"));
      }
    }
  }

  return buffers;
}

export async function editWithGemini3Pro(
  imageBuffer: Buffer,
  prompt: string,
  count: number,
  width: number,
  height: number,
): Promise<Buffer[]> {
  const aspectRatio = aspectRatioFor(width, height);

  const outputs = await Promise.all(
    Array.from({ length: Math.max(1, count) }, async () => {
      const res = await fetch(`${GEMINI_API}/models/${GEMINI_IMAGE_MODEL}:generateContent`, {
        method: "POST",
        headers: {
          "x-goog-api-key": key(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          contents: [
            {
              role: "user",
              parts: [
                { text: prompt },
                {
                  inline_data: {
                    mime_type: "image/png",
                    data: imageBuffer.toString("base64"),
                  },
                },
              ],
            },
          ],
          generationConfig: {
            responseModalities: ["TEXT", "IMAGE"],
            imageConfig: {
              aspectRatio,
              imageSize: "2K",
            },
            temperature: 0.35,
          },
        }),
      });

      const data = (await res.json()) as Record<string, unknown>;
      if (!res.ok) {
        const message =
          ((data.error as Record<string, unknown> | undefined)?.message as string | undefined) ||
          "Gemini 3 Pro image edit failed.";
        throw new Error(message);
      }

      return extractInlineImageBuffers(data);
    }),
  );

  return outputs.flat();
}
