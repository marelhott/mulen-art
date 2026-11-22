"""Prompts and plans of Varianty and Koláž, ported verbatim from Mulen Nano (utils/variantsPlan.ts, utils/collagePlan.ts).

The English wording is deliberate: the models react best to it. Pure functions, no I/O.
"""
import math

DISTANCES = ("near", "middle", "far", "weird")

GENERAL_PROMPT = """Create a new image from the same series as the attached image — a sibling, not a copy and not a different picture.

KEEP, exactly as in the original:
- the identity and character of the subject, including its oddities, ambiguity and imperfections; do not correct, idealise or make it more realistic or more normal
- the medium and technique (photograph, painting, print, drawing), the surface texture, grain and level of softness or sharpness
- the colour palette and tonal balance, the quality of light, the contrast
- the mood and emotional tone, the psychological presence
- the aspect ratio

CHANGE:
- the composition, camera angle or viewpoint, the pose or the direction of the gaze, the distance and the framing
- small details of the surroundings, so that it reads as another frame taken moments later or from another side

The result must feel unmistakably made by the same hand and in the same session, yet it must not repeat the original's composition.
Do not add text, captions, borders, watermarks or unrelated objects. Do not stylise, beautify or "fix" anything. Output one image."""

DISTANCE_SUFFIX = {
    "near": "Keep the change subtle: same pose family, slightly different angle.",
    "middle": None,
    "far": "Change the pose and composition strongly while keeping everything listed under KEEP.",
    "weird": "Make it genuinely weird: push the scene into the strange and uncanny — dream logic, unexpected scale, odd juxtapositions, distorted space, something quietly wrong or impossible — while the identity of the subject and everything listed under KEEP (medium, palette, light, mood) stays recognisably the same hand.",
}

EDIT_DIRECTIVES = {
    "near": [
        "Change the camera angle slightly, a few degrees to the left. Keep the same pose.",
        "Reframe slightly: crop a little tighter and move the subjects a little off-center.",
        "Change the direction of the gaze and the tilt of the head slightly. Keep the body pose.",
        "Change the camera angle slightly to the right and raise the viewpoint a little.",
        "Relax the pose a little: adjust the arms and hands slightly.",
    ],
    "middle": [
        "Change the camera to a different viewpoint: show the same scene from the left side at eye level.",
        "Reframe as a closer shot of the main subjects from a slightly lower angle.",
        "Change the pose and the gaze: the subjects turn toward the camera.",
        "Show the same scene from the right side with a wider framing.",
        "Change the viewpoint to a higher angle looking slightly down and change the pose a little.",
    ],
    "far": [
        "Show the same people from a completely different camera position: a low angle from the side, with clearly different poses.",
        "Shoot the scene from behind and above, with the people in different poses.",
        "Change to a wide shot from far away, with the people in clearly different positions and poses.",
        "Change to a tight close-up of one subject with a different head and body pose.",
        "Rotate the viewpoint about 90 degrees around the subjects and change everyone's pose.",
    ],
    "weird": [
        "Make the scene surreal: distort the proportions and scale of the subjects so that the space feels dreamlike.",
        "Make it uncanny: stretch the perspective and add one impossible, quietly wrong detail to the surroundings.",
        "Warp the space so the subjects seem to float and lean at impossible angles, in a dream-like way.",
        "Repeat and echo one of the subjects as a faint ghost-like double in the background.",
        "Change the scale of the room around the subjects so that it feels vast and unreal.",
    ],
}
EDIT_KEEP_SUFFIX = "Keep the same people and the same photographic style and lighting."


def is_instruction_edit_model(model: str) -> bool:
    """Qwen Edit (Venice) is an instruction editor: a generation prompt like "make a sibling, keep everything" returns the same picture."""
    return model.startswith("venice/qwen-")


def build_variants_prompt(base: str, distance: str) -> str:
    text = (base or "").strip() or GENERAL_PROMPT
    suffix = DISTANCE_SUFFIX[distance]
    return f"{text}\n\n{suffix}" if suffix else text


def build_edit_instruction(base: str, distance: str, variant_index: int) -> str:
    directives = EDIT_DIRECTIVES[distance]
    directive = directives[variant_index % len(directives)]
    return " ".join(part for part in [(base or "").strip(), directive, EDIT_KEEP_SUFFIX] if part)


def build_prompt_for_model(model: str, base: str, distance: str, variant_index: int) -> str:
    if is_instruction_edit_model(model):
        return build_edit_instruction(base, distance, variant_index)
    return build_variants_prompt(base, distance)


# --- Koláž ---------------------------------------------------------------------------------------------------------
FIDELITY_RULES = """FIDELITY RULES (most important):
- keep the medium of the sources: if they are photographs the result is a photograph with the same grain, colour and light; never repaint it as an illustration, oil painting or fantasy art
- add NOTHING that is not in the sources: no new objects, creatures, plants, water, buildings, effects, sparkles or decoration
- keep every subject whole, recognisable and unchanged in identity (faces, shapes, colours, textures stay as in the source); no hybrids, no creatures made of two things
- do not restyle, recolour, smooth or "improve" anything"""

COLLAGE_GENERAL_PROMPT = f"""Fuse the attached images into ONE organic picture. One image is the carrier (about 70% of the frame); the other flows into it gently, in one place only, so that the two read as a single moment. Everything comes from the sources.

{FIDELITY_RULES}

HOW THEY MERGE:
- through what they already share: a matching tone, a line that continues from one image into the other, a similar shape, the same direction of light
- a soft, semi-transparent blend (like a careful double exposure) or a gradual dissolve exactly where the shared tone or line is, not a hard edge
- the entering subject must belong to the carrier's space: matching scale, perspective, light direction and shadows, with edges that dissolve into the surroundings instead of sitting on top of them
- one consistent light and perspective across the whole picture
- the rest of the picture stays calm and untouched; less is more

NEVER: patchwork, tiles, cut-outs, collage-style pasted pieces, hard seams, split screens, side-by-side placement, borders, frames, text, watermarks. Output one image."""

SINGLE_SOURCE_PROMPT = f"""Rework the attached image as a restrained, organic fusion of its own two strongest ideas (for example its subject and its surroundings). Everything comes from the image itself.

{FIDELITY_RULES}

HOW THEY MERGE: through what they already share (a tone, a line, a shape, the direction of light), by a soft semi-transparent blend or a gradual dissolve in one place only; one light, one perspective; the rest stays calm. Less is more.

NEVER: patchwork, tiles, cut-outs, hard seams, repeating the source, borders, text, watermarks. Output one image."""

TECHNIQUES = [
    "Technique: careful double exposure. One image shows through the other with soft, partial transparency, aligned on a shared shape or line.",
    "Technique: continuing line. A contour or line from one image carries on into the other, and the picture changes character along that line.",
    "Technique: tonal dissolve. The two images dissolve into each other across a band of shared tone, with no visible seam.",
    "Technique: shared light. The second image enters through the area where both have the same light, and nowhere else.",
    "Technique: quiet inset. A small, precisely placed part of the second image blends into the first at a point where their shapes rhyme.",
]
ENTRY_ZONES = ["the upper part of the frame", "the left side", "the right side", "the lower part of the frame", "the horizon or the middle band", "the centre"]
ASPECTS = [("9:16", 9 / 16), ("2:3", 2 / 3), ("3:4", 3 / 4), ("4:5", 4 / 5), ("1:1", 1.0), ("5:4", 5 / 4), ("4:3", 4 / 3), ("3:2", 3 / 2), ("16:9", 16 / 9)]


def nearest_aspect_ratio(width: int, height: int) -> str:
    if not (width > 0 and height > 0):
        return "Original"
    ratio = width / height
    return min(ASPECTS, key=lambda item: abs(math.log(item[1] / ratio)))[0]


def pick_technique(seed: int) -> str:
    return TECHNIQUES[int(seed) % len(TECHNIQUES)]


def build_fuse_directive(seed: int, image_count: int) -> tuple[int, str]:
    """(shift, text): which input is the carrier, where the rest enters and the technique; every model gets a different mix."""
    n = max(1, image_count)
    seed = int(seed)
    shift = seed % n
    zone = ENTRY_ZONES[(seed // 2) % len(ENTRY_ZONES)]
    others = "The other attached images" if n > 1 else "The second idea"
    return shift, f"This variant: the carrier is the FIRST attached image. {others} enter it through {zone}, and the rest of the frame stays untouched.\n{pick_technique(seed)}"


def build_single_source_prompt(base: str, technique: str | None = None) -> str:
    text = (base or "").strip()
    if text:
        return text
    return f"{SINGLE_SOURCE_PROMPT}\n\n{technique}" if technique else SINGLE_SOURCE_PROMPT


def build_collage_edit_instruction(image_count: int) -> str:
    others = "image 2" if image_count <= 2 else "images " + " and ".join(str(i) for i in range(2, image_count + 1))
    verb = "blends" if image_count <= 2 else "blend"
    return (f"Edit image 1 so that {others} {verb} gently into it in one place only: keep image 1 as the carrier (about 70% of the frame), keep the medium, "
            "grain, colour and light of the sources, add nothing that is not in them, keep every subject whole and recognisable, and merge them through a "
            "shared tone, line or shape with a soft semi-transparent blend or dissolve. No cut-outs, no hard seams, no new objects, no repainting. Less is more.")


def rotate_inputs(items: list, index: int) -> list:
    if not items:
        return items
    shift = index % len(items)
    return items[shift:] + items[:shift]


def build_fuse_prompt(model: str, custom: str, seed: int, image_count: int) -> tuple[int, str]:
    """(shift, prompt) of one fused collage. A custom prompt is never altered."""
    shift, text = build_fuse_directive(seed, image_count)
    if (custom or "").strip():
        return shift, custom.strip()
    body = f"{COLLAGE_GENERAL_PROMPT}\n\n{text}"
    if is_instruction_edit_model(model):
        body = f"{build_collage_edit_instruction(image_count)}\n\n{body}"
    return shift, body
