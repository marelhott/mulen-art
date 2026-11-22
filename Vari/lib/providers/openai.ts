import type { Distance } from "../engines";

const OPENAI_API = "https://api.openai.com/v1";

function key(): string {
  const t = process.env.OPENAI_API_KEY;
  if (!t) {
    throw new Error("Chybí OPENAI_API_KEY v prostředí. Vision Remix bez něj nepoběží.");
  }
  return t;
}

export type VisionAnalysis = {
  subject: string;
  scene: string;
  composition: string;
  framing: string;
  perspective: string;
  palette: string;
  light: string;
  medium: string;
  texture: string;
  mood: string;
  immutable_elements: string[];
  variable_elements: string[];
  summary: string;
};

function extractResponseText(data: Record<string, unknown>): string {
  if (typeof data.output_text === "string" && data.output_text.trim()) {
    return data.output_text.trim();
  }

  const outputs = Array.isArray(data.output) ? data.output : [];
  const chunks: string[] = [];
  for (const output of outputs) {
    if (!output || typeof output !== "object") continue;
    const content = Array.isArray((output as Record<string, unknown>).content)
      ? ((output as Record<string, unknown>).content as Array<Record<string, unknown>>)
      : [];
    for (const item of content) {
      const text = item.text;
      if (typeof text === "string" && text.trim()) chunks.push(text.trim());
    }
  }
  return chunks.join("\n").trim();
}

function parseJsonObject(text: string): Record<string, unknown> {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) throw new Error("Vision model nevrátil JSON analýzu.");
  return JSON.parse(match[0]) as Record<string, unknown>;
}

function cleanString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function cleanStringArray(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) return fallback;
  const items = value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim());
  return items.length ? items : fallback;
}

function normalizeAnalysis(data: Record<string, unknown>): VisionAnalysis {
  return {
    subject: cleanString(data.subject, "main subject and its defining forms"),
    scene: cleanString(data.scene, "the depicted scene and environment"),
    composition: cleanString(data.composition, "balanced but distinctive composition"),
    framing: cleanString(data.framing, "medium framing"),
    perspective: cleanString(data.perspective, "eye-level perspective"),
    palette: cleanString(data.palette, "muted, coherent palette"),
    light: cleanString(data.light, "soft directional light"),
    medium: cleanString(data.medium, "image with tactile material character"),
    texture: cleanString(data.texture, "visible surface texture and edge behavior"),
    mood: cleanString(data.mood, "quiet but charged atmosphere"),
    immutable_elements: cleanStringArray(data.immutable_elements, [
      "the core subject identity",
      "the image's atmosphere",
      "the key material and spatial logic",
    ]),
    variable_elements: cleanStringArray(data.variable_elements, [
      "crop",
      "camera angle",
      "secondary supporting details",
    ]),
    summary: cleanString(data.summary, "A faithful but newly generated variant of the source image."),
  };
}

export async function analyzeImageForVariant(sourceUrl: string): Promise<VisionAnalysis> {
  const res = await fetch(`${OPENAI_API}/responses`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4.1-mini",
      input: [
        {
          role: "user",
          content: [
            {
              type: "input_text",
              text:
                "Analyze this image for a variant-generation pipeline. Return JSON only, no markdown. " +
                'Keys: subject, scene, composition, framing, perspective, palette, light, medium, texture, mood, immutable_elements, variable_elements, summary. ' +
                "immutable_elements and variable_elements must be arrays of short strings. Focus on what must stay recognizable across real variants, not on generic captioning.",
            },
            {
              type: "input_image",
              image_url: sourceUrl,
              detail: "high",
            },
          ],
        },
      ],
      max_output_tokens: 900,
    }),
  });

  const data = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    const message =
      ((data.error as Record<string, unknown> | undefined)?.message as string | undefined) ||
      "OpenAI vision request failed.";
    throw new Error(message);
  }

  return normalizeAnalysis(parseJsonObject(extractResponseText(data)));
}

function variationDirective(distance: Distance): string {
  switch (distance) {
    case "locked":
      return "Create a near-match variant. Keep the same subject, same scene logic, nearly the same composition, and only subtle differences in gesture, spacing, texture emphasis, or tiny environmental details.";
    case "sibling":
      return "Create a sibling image from the same series. Keep the same subject, atmosphere, and visual world, but change the crop, angle, spacing, or moment enough that it reads as a distinct neighboring work, not a duplicate.";
    case "looser":
      return "Create a looser but still clearly related variant. Preserve the same subject identity, atmosphere, palette logic, and material feel, while deliberately changing the composition, reframing the space, and redistributing visual weight.";
    case "new-frame":
      return "Create a new frame from the same world. Preserve the same subject identity, atmosphere, and visual logic, but use a substantially different composition, viewpoint, arrangement, and surrounding scene structure.";
  }
}

export function buildVisionRemixPrompt(distance: Distance, analysis: VisionAnalysis): string {
  return [
    "Generate an original image that is a true variant of the analyzed source, not a style transfer and not a literal copy.",
    variationDirective(distance),
    `Core subject: ${analysis.subject}.`,
    `Scene: ${analysis.scene}.`,
    `Composition: ${analysis.composition}.`,
    `Framing: ${analysis.framing}.`,
    `Perspective: ${analysis.perspective}.`,
    `Palette: ${analysis.palette}.`,
    `Light: ${analysis.light}.`,
    `Medium and material character: ${analysis.medium}.`,
    `Texture and surface behavior: ${analysis.texture}.`,
    `Mood: ${analysis.mood}.`,
    `These elements must remain recognizable: ${analysis.immutable_elements.join(", ")}.`,
    `These elements may change: ${analysis.variable_elements.join(", ")}.`,
    distance === "locked"
      ? "For this mode, staying very close is correct, but it still must read as a fresh rendering rather than the same image duplicated."
      : "Do not repeat the exact original silhouette, crop, subject placement, horizon line, or mass distribution.",
    distance === "sibling"
      ? "This should feel like the next work in the series, not the same frame rendered again. Change the crop, camera placement, and local relationships enough that the image is recognizably new."
      : "",
    distance === "looser" || distance === "new-frame"
      ? "A clearly different composition is required. Move masses, change spatial relationships, change framing logic, and avoid reconstructing the original layout from memory."
      : "",
    "Use the reference image to preserve identity, medium, atmosphere, and world logic.",
    "Use the text guidance to decide what should change.",
    "If the reference and prompt conflict, keep the same world and subject identity but prefer a newly recomposed image over a copied composition.",
    "Do not turn it into a generic illustration, poster, logo, simplified concept art, polished stock image, or glossy commercial render.",
    "Avoid beautifying the source into something cleaner, more perfect, or more expensive-looking than it really is.",
    "Preserve the image's tension, ambiguity, roughness, and specific material intelligence.",
  ].join(" ");
}

export async function analyzeVisionRemix(sourceUrl: string, distance: Distance) {
  const analysis = await analyzeImageForVariant(sourceUrl);
  const prompt = buildVisionRemixPrompt(distance, analysis);
  return { analysis, prompt };
}

export function buildGptImage2Prompt(distance: Distance, analysis: VisionAnalysis): string {
  const distanceInstruction =
    distance === "locked"
      ? "Create an almost-identical companion frame. Keep the same subject, world, atmosphere, palette logic, material quality, and compositional intent, with only subtle changes in crop, gesture, spacing, and local detail."
      : distance === "sibling"
        ? "Create a true sibling shot from the same series. Keep the same subject identity, same world, same atmosphere, same palette, and same medium, but make it a distinct neighboring frame with a changed crop, angle, spatial balance, and moment."
        : distance === "looser"
          ? "Create a looser but clearly related frame. Preserve subject identity, world, palette logic, atmosphere, medium, and material intelligence, while changing the composition, camera distance, spatial arrangement, and local relationships."
          : "Create a new frame from the same world. Preserve subject identity, atmosphere, palette logic, medium, and underlying visual intelligence, but produce a clearly different shot with a significantly different viewpoint, arrangement, crop, and composition.";

  return [
    "Edit the provided image into a new image variant.",
    "This must be a real variant, not a filter, not a cleanup pass, and not a literal duplicate.",
    distanceInstruction,
    `Subject identity to preserve: ${analysis.subject}.`,
    `World and scene to preserve: ${analysis.scene}.`,
    `Composition to respect but not copy exactly: ${analysis.composition}.`,
    `Framing baseline: ${analysis.framing}.`,
    `Perspective baseline: ${analysis.perspective}.`,
    `Palette logic: ${analysis.palette}.`,
    `Lighting logic: ${analysis.light}.`,
    `Medium and material character: ${analysis.medium}.`,
    `Texture and surface behavior: ${analysis.texture}.`,
    `Mood: ${analysis.mood}.`,
    `Must stay recognizable: ${analysis.immutable_elements.join(", ")}.`,
    `May change: ${analysis.variable_elements.join(", ")}.`,
    "Do not beautify, commercialize, or sanitize the source.",
    "Do not turn it into glossy concept art, a stock photo, a logo, a poster, a vector simplification, or a generic illustration.",
    "Preserve roughness, ambiguity, imperfection, and the source image's specific visual intelligence.",
    distance === "locked"
      ? "It should feel extremely close, but still like a fresh neighboring frame."
      : "Do not repeat the exact original silhouette, crop, subject placement, or mass distribution.",
  ].join(" ");
}

export async function editWithGptImage2(
  imageBuffer: Buffer,
  prompt: string,
  count: number,
  size: string,
) {
  const form = new FormData();
  form.append("model", "gpt-image-2");
  form.append("prompt", prompt);
  form.append("n", String(count));
  form.append("size", size);
  form.append("quality", "high");
  form.append("background", "auto");
  form.append("output_format", "png");
  form.append("image", new Blob([new Uint8Array(imageBuffer)], { type: "image/png" }), "source.png");

  const res = await fetch(`${OPENAI_API}/images/edits`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key()}`,
    },
    body: form,
  });

  const data = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    const message =
      ((data.error as Record<string, unknown> | undefined)?.message as string | undefined) ||
      "OpenAI GPT Image 2 edit failed.";
    throw new Error(message);
  }

  const items = Array.isArray(data.data) ? data.data : [];
  return items
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const b64 = (item as Record<string, unknown>).b64_json;
      return typeof b64 === "string" && b64.length > 0 ? Buffer.from(b64, "base64") : null;
    })
    .filter(Boolean) as Buffer[];
}
