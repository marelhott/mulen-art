"""Vari: engines, distances, prompts and provider payload builders.

A faithful port of the TypeScript in Vari/lib (engines/*, prompts.ts, image-info.ts, the prompt builders of
providers/openai.ts). tests/test_vari.py reproduces tests/fixtures/vari_payloads.json, which was produced by the
original TypeScript (Vari/scripts/dump-payloads.ts), so any drift in version hashes, clamps or per-distance
tuning fails a test.
"""
import json
import math
import random
from typing import Any, Callable

DISTANCES = ["locked", "sibling", "looser", "new-frame"]
DISTANCE_LABELS = {
    "locked": "co nejblíž originálu",
    "sibling": "další záběr ze stejné série",
    "looser": "volnější, ale pořád příbuzné",
    "new-frame": "jiný záběr stejného světa",
}

# Order as in the original UI. `keys` are the environment variables an engine needs (all of them).
ENGINES: dict[str, dict[str, Any]] = {
    "sd-variation": {"label": "SD Image Variation", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN"]},
    "gpt-image-2": {"label": "GPT Image 2", "provider": "openai", "keys": ["OPENAI_API_KEY"]},
    "gemini-3-pro": {"label": "Gemini 3 Pro", "provider": "gemini", "keys": ["GEMINI_API_KEY", "OPENAI_API_KEY"]},
    "z-image": {"label": "Z-Image", "provider": "fal", "keys": ["FAL_KEY"]},
    "grok-imagine": {"label": "Grok Imagine", "provider": "fal", "keys": ["FAL_KEY"]},
    "vision-remix": {"label": "Vision Remix", "provider": "fal", "keys": ["FAL_KEY", "OPENAI_API_KEY"]},
    "ip-adapter-sdxl": {"label": "IP-Adapter SDXL", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN"]},
    "chigozienri-ip-adapter-sdxl": {"label": "chigozienri/ip_adapter-sdxl", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN"]},
    "unclip": {"label": "Stable unCLIP", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN"]},
    "comfy-unclip": {"label": "Comfy IPAdapter", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN", "FAL_KEY"]},
    "sdxl-artistic": {"label": "SDXL Artistic (exp)", "provider": "fal", "keys": ["FAL_KEY"]},
    "stable": {"label": "Stable Variation (slow)", "provider": "fal", "keys": ["FAL_KEY"]},
    "fofr-any-comfyui-workflow": {"label": "fofr/any-comfyui-workflow", "provider": "replicate", "keys": ["REPLICATE_API_TOKEN"]},
}

# Optional per-engine tuning (payload field -> (context key, minimum, maximum, step, default text for the UI)).
TUNING: dict[str, list[dict[str, Any]]] = {
    "sd-variation": [
        {"key": "sd_variation_guidance", "label": "Guidance", "min": 1, "max": 8, "step": 0.1},
        {"key": "sd_variation_steps", "label": "Kroky", "min": 10, "max": 60, "step": 1},
    ],
    "z-image": [{"key": "z_image_creativity", "label": "Kreativita", "min": 0.1, "max": 1, "step": 0.01}],
    "ip-adapter-sdxl": [
        {"key": "ip_adapter_scale", "label": "Vliv obrazu", "min": 0.1, "max": 1.2, "step": 0.01},
        {"key": "ip_adapter_steps", "label": "Kroky", "min": 20, "max": 80, "step": 1},
    ],
    "chigozienri-ip-adapter-sdxl": [
        {"key": "chigo_scale", "label": "Vliv obrazu", "min": 0.1, "max": 1.2, "step": 0.01},
        {"key": "chigo_steps", "label": "Kroky", "min": 20, "max": 100, "step": 1},
    ],
    "comfy-unclip": [
        {"key": "comfy_noise", "label": "Šum", "min": 0, "max": 0.35, "step": 0.01},
        {"key": "comfy_strength", "label": "Síla", "min": 0.35, "max": 1, "step": 0.01},
    ],
    "sdxl-artistic": [
        {"key": "sdxl_guidance", "label": "Guidance", "min": 1, "max": 8, "step": 0.1},
        {"key": "sdxl_strength", "label": "Síla", "min": 0.2, "max": 0.95, "step": 0.01},
        {"key": "sdxl_steps", "label": "Kroky", "min": 10, "max": 60, "step": 1},
    ],
    "stable": [
        {"key": "stable_guidance", "label": "Guidance", "min": 1, "max": 8, "step": 0.1},
        {"key": "stable_strength", "label": "Síla", "min": 0.2, "max": 0.98, "step": 0.01},
        {"key": "stable_steps", "label": "Kroky", "min": 10, "max": 60, "step": 1},
    ],
    "fofr-any-comfyui-workflow": [
        {"key": "fofr_cfg", "label": "CFG", "min": 1, "max": 8, "step": 0.1},
        {"key": "fofr_steps", "label": "Kroky", "min": 20, "max": 80, "step": 1},
        {"key": "fofr_ip_weight", "label": "Váha IP-Adapteru", "min": 0.2, "max": 1.1, "step": 0.01},
    ],
}
TUNING_KEYS = {item["key"] for items in TUNING.values() for item in items}

MAX_PER_CALL = {"sd-variation": 4, "z-image": 4, "grok-imagine": 4, "ip-adapter-sdxl": 4, "chigozienri-ip-adapter-sdxl": 4,
                "gpt-image-2": 4, "gemini-3-pro": 4, "vision-remix": 4}
DEFAULT_MAX_PER_CALL = 12


def availability(environ) -> dict[str, dict[str, Any]]:
    """Which engines can run with the keys present in `environ` (the keys themselves are never exposed)."""
    result = {}
    for engine, spec in ENGINES.items():
        missing = [key for key in spec["keys"] if not environ.get(key)]
        # A dead key is only discovered by calling the provider; it surfaces as that job's error.
        result[engine] = {"id": engine, "name": spec["label"], "provider": spec["provider"], "available": not missing,
                          "missing": missing, "tuning": TUNING.get(engine, [])}
    return result


# ---------------------------------------------------------------------------------------------- numbers (JS semantics)

def js_round(value: float) -> int:
    """Math.round: halves go up (Python's round() goes to even)."""
    return math.floor(value + 0.5)


def clean(value: Any) -> Any:
    """Floats with an integral value become ints, so JSON matches JS (`3` not `3.0`)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def js_json(value: Any) -> str:
    """JSON.stringify: compact separators, integral floats printed as integers."""
    return json.dumps(clean(value), separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------------------------- image info

SUPPORTED_RATIOS = [("1:1", 1), ("2:3", 2 / 3), ("3:2", 3 / 2), ("3:4", 3 / 4), ("4:3", 4 / 3), ("4:5", 4 / 5),
                    ("5:4", 5 / 4), ("9:16", 9 / 16), ("16:9", 16 / 9)]


def image_info(width: int, height: int) -> dict[str, Any]:
    width, height = width or 1024, height or 1024
    source_ratio = width / height
    nearest = SUPPORTED_RATIOS[0]
    for candidate in SUPPORTED_RATIOS:
        if abs(candidate[1] - source_ratio) < abs(nearest[1] - source_ratio):
            nearest = candidate
    return {"width": width, "height": height, "aspectRatio": nearest[0]}


def fal_image_size(info: dict[str, Any]) -> str:
    ratio = info["width"] / info["height"]
    if abs(ratio - 1) < 0.05:
        return "square"
    if ratio >= 1.6:
        return "landscape_16_9"
    if ratio <= 1 / 1.6:
        return "portrait_16_9"
    return "landscape_4_3" if ratio >= 1 else "portrait_4_3"


def snapped_dimensions(info: dict[str, Any], long_side: int = 1024) -> dict[str, int]:
    ratio = info["width"] / info["height"]
    if ratio >= 1:
        return {"width": long_side, "height": max(512, js_round((long_side / ratio) / 64) * 64)}
    return {"width": max(512, js_round((long_side * ratio) / 64) * 64), "height": long_side}


# ---------------------------------------------------------------------------------------------- prompts

DISTANCE_PROMPTS = {
    "locked": "Another frame from the same artistic series as the attached source. Preserve the source's exact atmosphere, palette, materiality, ambiguity, grain, and any painterly or photographic defects. Treat all imperfections as intentional. Make it feel like the next exposure from the same session.",
    "sibling": "A different frame from the same artistic series as the attached source. Keep the palette, mood, material defects, texture and visual register. Vary only the exact pose, framing, and moment. Do not resolve the source's ambiguity into photorealism.",
    "looser": "A substantially different frame that is still clearly from the same artistic series as the attached source. Preserve palette, atmosphere, visual defects and emotional register. Change pose, framing, angle, lighting moment and micro-composition. This must not be a near-copy or direct repaint of the source.",
    "new-frame": "Use the attached source only as an artistic reference, not as an image to preserve. Generate a different frame from the same series and world: related subject, related palette, related atmosphere, related material imperfection and ambiguity, but a clearly different frame, different pose, different camera distance, different crop and different instant. Keep the original's unresolved visual character, do not clean it up.",
}
NEGATIVE_PROMPT = "photorealistic cleanup, realism enhancement, face restoration, beauty retouch, sharpen, crisp detail, polished commercial finish, HDR, hyperrealism, clean skin, restoration, glamour, perfect anatomy, commercial photo, studio lighting"
ANTI_DUPLICATE = "near copy, duplicate, same image, direct repaint, exact pose, exact crop, exact framing"


def build_prompt(distance: str) -> tuple[str, str]:
    prompt = DISTANCE_PROMPTS.get(distance, DISTANCE_PROMPTS["sibling"])
    negative = f"{NEGATIVE_PROMPT}, {ANTI_DUPLICATE}" if distance in ("looser", "new-frame") else NEGATIVE_PROMPT
    return prompt, negative


def _variation_directive(distance: str) -> str:
    return {
        "locked": "Create a near-match variant. Keep the same subject, same scene logic, nearly the same composition, and only subtle differences in gesture, spacing, texture emphasis, or tiny environmental details.",
        "sibling": "Create a sibling image from the same series. Keep the same subject, atmosphere, and visual world, but change the crop, angle, spacing, or moment enough that it reads as a distinct neighboring work, not a duplicate.",
        "looser": "Create a looser but still clearly related variant. Preserve the same subject identity, atmosphere, palette logic, and material feel, while deliberately changing the composition, reframing the space, and redistributing visual weight.",
        "new-frame": "Create a new frame from the same world. Preserve the same subject identity, atmosphere, and visual logic, but use a substantially different composition, viewpoint, arrangement, and surrounding scene structure.",
    }[distance]


def build_vision_remix_prompt(distance: str, a: dict[str, Any]) -> str:
    return " ".join([
        "Generate an original image that is a true variant of the analyzed source, not a style transfer and not a literal copy.",
        _variation_directive(distance),
        f"Core subject: {a['subject']}.",
        f"Scene: {a['scene']}.",
        f"Composition: {a['composition']}.",
        f"Framing: {a['framing']}.",
        f"Perspective: {a['perspective']}.",
        f"Palette: {a['palette']}.",
        f"Light: {a['light']}.",
        f"Medium and material character: {a['medium']}.",
        f"Texture and surface behavior: {a['texture']}.",
        f"Mood: {a['mood']}.",
        f"These elements must remain recognizable: {', '.join(a['immutable_elements'])}.",
        f"These elements may change: {', '.join(a['variable_elements'])}.",
        "For this mode, staying very close is correct, but it still must read as a fresh rendering rather than the same image duplicated."
        if distance == "locked"
        else "Do not repeat the exact original silhouette, crop, subject placement, horizon line, or mass distribution.",
        "This should feel like the next work in the series, not the same frame rendered again. Change the crop, camera placement, and local relationships enough that the image is recognizably new."
        if distance == "sibling" else "",
        "A clearly different composition is required. Move masses, change spatial relationships, change framing logic, and avoid reconstructing the original layout from memory."
        if distance in ("looser", "new-frame") else "",
        "Use the reference image to preserve identity, medium, atmosphere, and world logic.",
        "Use the text guidance to decide what should change.",
        "If the reference and prompt conflict, keep the same world and subject identity but prefer a newly recomposed image over a copied composition.",
        "Do not turn it into a generic illustration, poster, logo, simplified concept art, polished stock image, or glossy commercial render.",
        "Avoid beautifying the source into something cleaner, more perfect, or more expensive-looking than it really is.",
        "Preserve the image's tension, ambiguity, roughness, and specific material intelligence.",
    ])


def build_gpt_image2_prompt(distance: str, a: dict[str, Any]) -> str:
    instruction = {
        "locked": "Create an almost-identical companion frame. Keep the same subject, world, atmosphere, palette logic, material quality, and compositional intent, with only subtle changes in crop, gesture, spacing, and local detail.",
        "sibling": "Create a true sibling shot from the same series. Keep the same subject identity, same world, same atmosphere, same palette, and same medium, but make it a distinct neighboring frame with a changed crop, angle, spatial balance, and moment.",
        "looser": "Create a looser but clearly related frame. Preserve subject identity, world, palette logic, atmosphere, medium, and material intelligence, while changing the composition, camera distance, spatial arrangement, and local relationships.",
        "new-frame": "Create a new frame from the same world. Preserve subject identity, atmosphere, palette logic, medium, and underlying visual intelligence, but produce a clearly different shot with a significantly different viewpoint, arrangement, crop, and composition.",
    }[distance]
    return " ".join([
        "Edit the provided image into a new image variant.",
        "This must be a real variant, not a filter, not a cleanup pass, and not a literal duplicate.",
        instruction,
        f"Subject identity to preserve: {a['subject']}.",
        f"World and scene to preserve: {a['scene']}.",
        f"Composition to respect but not copy exactly: {a['composition']}.",
        f"Framing baseline: {a['framing']}.",
        f"Perspective baseline: {a['perspective']}.",
        f"Palette logic: {a['palette']}.",
        f"Lighting logic: {a['light']}.",
        f"Medium and material character: {a['medium']}.",
        f"Texture and surface behavior: {a['texture']}.",
        f"Mood: {a['mood']}.",
        f"Must stay recognizable: {', '.join(a['immutable_elements'])}.",
        f"May change: {', '.join(a['variable_elements'])}.",
        "Do not beautify, commercialize, or sanitize the source.",
        "Do not turn it into glossy concept art, a stock photo, a logo, a poster, a vector simplification, or a generic illustration.",
        "Preserve roughness, ambiguity, imperfection, and the source image's specific visual intelligence.",
        "It should feel extremely close, but still like a fresh neighboring frame."
        if distance == "locked"
        else "Do not repeat the exact original silhouette, crop, subject placement, or mass distribution.",
    ])


# ---------------------------------------------------------------------------------------------- payload builders

def _by_distance(distance: str, values: tuple) -> Any:
    return values[DISTANCES.index(distance)]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _pick(ctx: dict[str, Any], key: str) -> Any:
    value = ctx.get(key)
    return value if _number(value) else None


def _build_sd_variation(ctx, rng):
    steps, guidance = _pick(ctx, "sd_variation_steps"), _pick(ctx, "sd_variation_guidance")
    return {"_provider": "replicate",
            "version": "7c399ba0e1b33ed8ec39ed30eb6b0a2d9e054462543c428c251293034af82a8e",
            "input": {"input_image": ctx["source_url"],
                      "num_outputs": max(1, min(4, js_round(ctx["count"]))),
                      "num_inference_steps": js_round(steps) if steps is not None else 25,
                      "guidance_scale": guidance if guidance is not None else _by_distance(ctx["distance"], (3.4, 3, 2.7, 2.4))}}


def _build_unclip(ctx, rng):
    new_frame = ctx["distance"] == "new-frame"
    return {"_provider": "replicate",
            "version": "3a8d2f4f25198c92beb3c633ed94f8013399509c7321cd09c9036c2e33c67617",
            "input": {"image": ctx["source_url"], "num_outputs": ctx["count"],
                      "num_inference_steps": 60 if new_frame else 50,
                      "guidance_scale": 5.8 if new_frame else 6.8, "scheduler": "DPMSolverMultistep"}}


def _build_stable(ctx, rng):
    prompt, negative = build_prompt(ctx["distance"])
    info, distance = ctx["image_info"], ctx["distance"]
    steps, guidance, strength = _pick(ctx, "stable_steps"), _pick(ctx, "stable_guidance"), _pick(ctx, "stable_strength")
    if info["aspectRatio"] == "1:1":
        size = "square"
    else:
        size = "landscape_4_3" if info["width"] >= info["height"] else "portrait_4_3"
    return {"_model_id": "fal-ai/stable-diffusion-v3-medium/image-to-image", "image_url": ctx["source_url"],
            "prompt": prompt, "negative_prompt": negative, "num_images": ctx["count"], "image_size": size,
            "num_inference_steps": js_round(steps) if steps is not None else 30,
            "guidance_scale": guidance if guidance is not None else (3.2 if distance == "new-frame" else 3.8),
            "strength": strength if strength is not None else (0.92 if distance == "new-frame" else 0.82 if distance == "looser" else 0.68),
            "enable_safety_checker": False}


def _build_z_image(ctx, rng):
    prompt, negative = build_prompt(ctx["distance"])
    distance = ctx["distance"]
    creativity = _pick(ctx, "z_image_creativity")
    return {"_model_id": "fal-ai/z-image/turbo/image-to-image", "image_url": ctx["source_url"], "prompt": prompt,
            "negative_prompt": negative, "num_images": min(ctx["count"], 4), "image_size": "auto",
            "num_inference_steps": _by_distance(distance, (8, 7, 6, 5)),
            "strength": creativity if creativity is not None else _by_distance(distance, (0.36, 0.5, 0.66, 0.8)),
            "acceleration": "none" if distance == "locked" else "regular",
            "enable_prompt_expansion": False, "enable_safety_checker": False, "output_format": "png"}


def _build_grok(ctx, rng):
    prompt, _ = build_prompt(ctx["distance"])
    return {"_model_id": "xai/grok-imagine-image/edit", "prompt": prompt, "image_urls": [ctx["source_url"]],
            "num_images": min(ctx["count"], 4), "resolution": "2k", "output_format": "png"}


def _build_sdxl_artistic(ctx, rng):
    prompt, negative = build_prompt(ctx["distance"])
    distance = ctx["distance"]
    size = snapped_dimensions(ctx["image_info"], 1280)
    guidance, steps, strength = _pick(ctx, "sdxl_guidance"), _pick(ctx, "sdxl_steps"), _pick(ctx, "sdxl_strength")
    return {"_model_id": "fal-ai/fast-sdxl/image-to-image", "image_url": ctx["source_url"], "prompt": prompt,
            "negative_prompt": negative, "num_images": ctx["count"], "image_size": size,
            "enable_safety_checker": False, "expand_prompt": False,
            "guidance_scale": guidance if guidance is not None else _by_distance(distance, (3.6, 3.2, 2.9, 2.6)),
            "num_inference_steps": js_round(steps) if steps is not None else _by_distance(distance, (40, 36, 32, 28)),
            "strength": strength if strength is not None else _by_distance(distance, (0.42, 0.5, 0.58, 0.66)),
            "format": "png"}


def _build_ip_adapter(ctx, rng):
    distance = ctx["distance"]
    scale, steps = _pick(ctx, "ip_adapter_scale"), _pick(ctx, "ip_adapter_steps")
    return {"_provider": "replicate",
            "version": "904dc004af1dba5c9b13fc9e41635aeb2f9a177896a396ab3393f3f6493dbdd4",
            "input": {"image": ctx["source_url"], "prompt": "", "negative_prompt": "", "num_outputs": min(ctx["count"], 4),
                      "num_inference_steps": js_round(steps) if steps is not None else _by_distance(distance, (55, 48, 44, 40)),
                      "scale": scale if scale is not None else _by_distance(distance, (0.82, 0.66, 0.52, 0.4))}}


def _build_chigozienri(ctx, rng):
    distance = ctx["distance"]
    scale, steps = _pick(ctx, "chigo_scale"), _pick(ctx, "chigo_steps")
    return {"_provider": "replicate",
            "version": "904dc004af1dba5c9b13fc9e41635aeb2f9a177896a396ab3393f3f6493dbdd4",
            "input": {"image": ctx["source_url"], "prompt": "", "negative_prompt": "", "num_outputs": min(ctx["count"], 4),
                      "num_inference_steps": js_round(steps) if steps is not None else _by_distance(distance, (80, 68, 58, 48)),
                      "scale": scale if scale is not None else _by_distance(distance, (0.92, 0.82, 0.68, 0.54))}}


def _ip_adapter_workflow(checkpoint, sampler, prefix, ctx, rng, steps, cfg, ip_weight, long_side):
    prompt, negative = build_prompt(ctx["distance"])
    size = snapped_dimensions(ctx["image_info"], long_side)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
        "3": {"class_type": "IPAdapterUnifiedLoader", "inputs": {"model": ["1", 0], "preset": "PLUS (high strength)"}},
        "4": {"class_type": "IPAdapter", "inputs": {"model": ["3", 0], "ipadapter": ["3", 1], "image": ["2", 0], "weight": ip_weight,
                                                    "start_at": 0, "end_at": 1, "weight_type": "standard"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": size["width"], "height": size["height"], "batch_size": ctx["count"]}},
        "8": {"class_type": "KSampler", "inputs": {"seed": math.floor(rng() * 1_000_000_000_000), "steps": steps, "cfg": cfg,
                                                    "sampler_name": sampler, "scheduler": "karras", "denoise": 1,
                                                    "model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                                                    "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["9", 0]}},
    }


def _build_comfy_unclip(ctx, rng):
    distance = ctx["distance"]
    cfg, steps = _by_distance(distance, ((3.2, 45), (2.8, 42), (2.5, 40), (2.3, 40)))
    noise_override, strength_override = _pick(ctx, "comfy_noise"), _pick(ctx, "comfy_strength")
    noise = max(0, min(0.35, noise_override)) if noise_override is not None else 0.21
    strength = max(0.35, min(1, strength_override)) if strength_override is not None else 0.86
    ip_weight = max(0.35, min(0.95, strength - noise * 0.35))
    workflow = _ip_adapter_workflow("v1-5-pruned-emaonly.ckpt", "dpmpp_2m", "variants-comfy-unclip", ctx, rng, steps, cfg, ip_weight, 1024)
    return {"_provider": "replicate",
            "version": "16d0a881fbfc066f0471a3519a347db456fe8cbcbd53abb435a50a74efaeb427",
            "input": {"workflow_json": js_json(workflow), "input_file": ctx.get("comfy_reference_url") or ctx["source_url"],
                      "return_temp_files": False, "output_format": "png", "output_quality": 95, "randomise_seeds": False}}


def _build_fofr(ctx, rng):
    distance = ctx["distance"]
    cfg0, steps0, weight0 = _by_distance(distance, ((3.6, 54, 0.86), (3.2, 48, 0.76), (2.9, 44, 0.64), (2.6, 40, 0.52)))
    cfg, steps, weight = _pick(ctx, "fofr_cfg"), _pick(ctx, "fofr_steps"), _pick(ctx, "fofr_ip_weight")
    workflow = _ip_adapter_workflow("sd_xl_base_1.0.safetensors", "dpmpp_2m_sde", "variants-fofr-sdxl-ipadapter", ctx, rng,
                                    js_round(steps) if steps is not None else steps0, cfg if cfg is not None else cfg0,
                                    weight if weight is not None else weight0, 1280)
    return {"_provider": "replicate",
            "version": "7896cf903d3fff4ac5edf2d46918a7a9e51ed7d6d4e0192ab1264587ada22692",
            "input": {"workflow_json": js_json(workflow), "input_file": ctx["source_url"], "return_temp_files": False,
                      "randomise_seeds": False}}


BUILDERS: dict[str, Callable[[dict[str, Any], Callable[[], float]], dict[str, Any]]] = {
    "sd-variation": _build_sd_variation,
    "z-image": _build_z_image,
    "grok-imagine": _build_grok,
    "ip-adapter-sdxl": _build_ip_adapter,
    "chigozienri-ip-adapter-sdxl": _build_chigozienri,
    "unclip": _build_unclip,
    "comfy-unclip": _build_comfy_unclip,
    "sdxl-artistic": _build_sdxl_artistic,
    "stable": _build_stable,
    "fofr-any-comfyui-workflow": _build_fofr,
}


def build_payload(engine: str, ctx: dict[str, Any], rng: Callable[[], float] = random.random) -> dict[str, Any]:
    return BUILDERS[engine](ctx, rng)
