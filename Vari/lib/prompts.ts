import type { Distance } from "./engines";

// Neutral, content-agnostic prompts. These must NOT describe the visible content
// of the source image. They describe META-qualities only: preserve atmosphere,
// palette, defects, ambiguity, and prevent photoreal cleanup. The source image
// is attached to every generation request, so the model sees the content
// directly through img2img / IP-Adapter / unCLIP conditioning — we do not need
// (and must not) re-describe it in text.
//
// The previous prompts hard-coded one specific series ("amber monochrome
// portrait, bloom, body") which corrupted generation for any other input
// type (landscape, glitch, painterly scene, etc.).

export const DISTANCE_PROMPTS: Record<Distance, string> = {
  locked:
    "Another frame from the same artistic series as the attached source. Preserve the source's exact atmosphere, palette, materiality, ambiguity, grain, and any painterly or photographic defects. Treat all imperfections as intentional. Make it feel like the next exposure from the same session.",
  sibling:
    "A different frame from the same artistic series as the attached source. Keep the palette, mood, material defects, texture and visual register. Vary only the exact pose, framing, and moment. Do not resolve the source's ambiguity into photorealism.",
  looser:
    "A substantially different frame that is still clearly from the same artistic series as the attached source. Preserve palette, atmosphere, visual defects and emotional register. Change pose, framing, angle, lighting moment and micro-composition. This must not be a near-copy or direct repaint of the source.",
  "new-frame":
    "Use the attached source only as an artistic reference, not as an image to preserve. Generate a different frame from the same series and world: related subject, related palette, related atmosphere, related material imperfection and ambiguity, but a clearly different frame, different pose, different camera distance, different crop and different instant. Keep the original's unresolved visual character, do not clean it up.",
};

export const NEGATIVE_PROMPT =
  "photorealistic cleanup, realism enhancement, face restoration, beauty retouch, sharpen, crisp detail, polished commercial finish, HDR, hyperrealism, clean skin, restoration, glamour, perfect anatomy, commercial photo, studio lighting";

// Extra negative used only for looser / new-frame where we want the model
// to actually diverge from the exact source frame.
export const ANTI_DUPLICATE =
  "near copy, duplicate, same image, direct repaint, exact pose, exact crop, exact framing";

export function buildPrompt(distance: Distance): { prompt: string; negativePrompt: string } {
  const prompt = DISTANCE_PROMPTS[distance] ?? DISTANCE_PROMPTS.sibling;
  const negativePrompt =
    distance === "looser" || distance === "new-frame"
      ? `${NEGATIVE_PROMPT}, ${ANTI_DUPLICATE}`
      : NEGATIVE_PROMPT;
  return { prompt, negativePrompt };
}
