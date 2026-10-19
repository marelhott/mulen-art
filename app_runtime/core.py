import base64
import gc
import io
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


QUALITY_TO_STEPS = {
    "fast": 15,
    "balanced": 25,
    "high": 35,
    "maximum": 50,
}

MIN_SCALE = 0.5
MAX_SCALE = 4.0
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.json"
SAMPLER_OPTIONS = {"dpmpp_2m", "euler_a", "ddim"}
SCHEDULE_OPTIONS = {"karras", "normal"}

CURRENT_MODEL_ID = None
CURRENT_PIPELINE = None
CURRENT_LORA_ID = "none"
CURRENT_LORA_STRENGTH = 0.0
MODEL_CONFIG = None
MODEL_CONFIG_MTIME_NS = None
TORCH_MODULE = None
DIFFUSERS_MODULES = None
ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class GenerationInput:
    image_base64: str
    model_id: str
    lora_id: str
    denoise: float
    lora_strength: float
    cfg: float
    steps: int
    sampler: str
    schedule: str
    scale: float
    num_images: int


def generate(payload: dict[str, Any], progress_callback: ProgressCallback | None = None,
             image_callback: Callable | None = None) -> dict[str, Any]:
    started = time.monotonic()
    generation_input = parse_input(payload)
    report_progress(progress_callback, 0.02, "Input validated")

    if use_demo_mode():
        return build_demo_response(generation_input, progress_callback)

    torch = get_torch()
    report_progress(progress_callback, 0.06, "Torch runtime ready")
    pipe = ensure_pipeline(generation_input.model_id)
    report_progress(progress_callback, 0.18, f"Model ready: {generation_input.model_id}")
    pipe.scheduler = make_scheduler(pipe.scheduler.config, generation_input.sampler, generation_input.schedule)
    report_progress(progress_callback, 0.22, f"Scheduler ready: {generation_input.sampler} / {generation_input.schedule}")
    ensure_lora(pipe, generation_input.lora_id, generation_input.lora_strength)
    report_progress(progress_callback, 0.28, f"LoRA ready: {generation_input.lora_id}")
    setup_seconds = time.monotonic() - started

    source_image = decode_image(generation_input.image_base64)
    source_image = normalize_dimensions(source_image)
    report_progress(progress_callback, 0.34, f"Source normalized to {source_image.width}x{source_image.height}")

    steps = generation_input.steps
    guidance_scale = generation_input.cfg
    output_images = []
    meta = {
        "model_id": generation_input.model_id, "lora_id": generation_input.lora_id,
        "denoise": generation_input.denoise, "lora_strength": generation_input.lora_strength,
        "steps": steps, "scale": generation_input.scale, "guidance_scale": guidance_scale,
        "sampler": generation_input.sampler, "schedule": generation_input.schedule,
        "demo_mode": False,
    }

    inference_started = time.monotonic()
    for index in range(generation_input.num_images):
        seed = random.randint(0, 2**31 - 1)
        generator = torch.Generator(device="cuda").manual_seed(seed)
        base_progress = 0.35 + (index / max(1, generation_input.num_images)) * 0.55
        report_progress(progress_callback, base_progress, f"Generating image {index + 1}/{generation_input.num_images}")
        result = pipe(
            prompt="",
            image=source_image,
            strength=generation_input.denoise,
            guidance_scale=guidance_scale,
            num_inference_steps=steps,
            generator=generator,
            callback_on_step_end=build_step_callback(progress_callback, base_progress, generation_input.num_images, index, steps),
            callback_on_step_end_tensor_inputs=[],
        ).images[0]

        result = upscale_if_needed(result, generation_input.scale)
        output_images.append(encode_image(result))
        if image_callback is not None:
            image_callback(output_images[-1], meta)
        report_progress(progress_callback, base_progress + 0.55 / max(1, generation_input.num_images), f"Image {index + 1}/{generation_input.num_images} saved")

    meta["setup_seconds"] = round(setup_seconds, 2)
    meta["generation_and_save_seconds"] = round(time.monotonic() - inference_started, 2)
    report_progress(progress_callback, 1.0, "Generation complete")
    return {
        "images": output_images,
        "meta": meta,
}


def get_options() -> dict[str, Any]:
    config = load_config()
    return {
        "models": [{"id": item["id"], "name": item["name"], "kind": item.get("kind", "checkpoint")} for item in config.get("models", [])],
        "loras": [{"id": item["id"], "name": item["name"]} for item in config.get("loras", [])],
        "samplers": [
            {"id": "dpmpp_2m", "name": "DPM++ 2M"},
            {"id": "euler_a", "name": "Euler a"},
            {"id": "ddim", "name": "DDIM"},
        ],
        "schedules": [
            {"id": "karras", "name": "Karras"},
            {"id": "normal", "name": "Normal"},
        ],
    }


def use_demo_mode() -> bool:
    return (
        os.getenv("IMG2IMG_DEMO_MODE", "false").lower() == "true"
    )


def get_torch():
    global TORCH_MODULE
    if TORCH_MODULE is None:
        import torch

        TORCH_MODULE = torch
    return TORCH_MODULE


def get_diffusers():
    global DIFFUSERS_MODULES
    if DIFFUSERS_MODULES is None:
        from diffusers import DDIMScheduler, DPMSolverMultistepScheduler, EulerAncestralDiscreteScheduler, StableDiffusionXLImg2ImgPipeline

        DIFFUSERS_MODULES = {
            "scheduler": DPMSolverMultistepScheduler,
            "ddim_scheduler": DDIMScheduler,
            "euler_a_scheduler": EulerAncestralDiscreteScheduler,
            "pipeline": StableDiffusionXLImg2ImgPipeline,
        }
    return DIFFUSERS_MODULES


def is_cuda_oom(exc: Exception) -> bool:
    return exc.__class__.__name__ == "OutOfMemoryError" and exc.__class__.__module__.startswith("torch")


def parse_input(payload: dict[str, Any]) -> GenerationInput:
    if not payload.get("image_base64"):
        raise ValueError("image_base64 is required.")

    scale = clamp(float(payload.get("scale", 1.0)), MIN_SCALE, MAX_SCALE)

    quality = str(payload.get("quality", "balanced")).lower()
    if quality not in QUALITY_TO_STEPS:
        quality = "balanced"

    sampler = str(payload.get("sampler", "dpmpp_2m")).lower()
    if sampler not in SAMPLER_OPTIONS:
        sampler = "dpmpp_2m"

    schedule = str(payload.get("schedule", "karras")).lower()
    if schedule not in SCHEDULE_OPTIONS:
        schedule = "karras"

    steps = int(clamp(int(payload.get("steps", QUALITY_TO_STEPS[quality])), 1, 150))
    cfg = clamp(float(payload.get("cfg", os.getenv("DEFAULT_GUIDANCE_SCALE", "1.8"))), 1.0, 20.0)

    model_id = str(payload.get("model_id", "tuymans_sdxl"))
    lora_id = str(payload.get("lora_id", "none"))
    model = get_config_item("models", model_id)
    get_config_item("loras", lora_id)
    if model.get("kind") == "base" and lora_id == "none":
        raise ValueError("Select a trained LoRA for SDXL Base.")
    if model.get("kind") != "base" and lora_id != "none":
        raise ValueError("Trained checkpoints run without LoRA. Use SDXL Base for LoRA mode.")

    raw_count = payload.get("num_images", 1)
    num_images = int(raw_count)
    if isinstance(raw_count, bool) or num_images < 1 or str(raw_count).strip() != str(num_images):
        raise ValueError("num_images must be a positive integer")

    return GenerationInput(
        image_base64=str(payload["image_base64"]),
        model_id=model_id,
        lora_id=lora_id,
        denoise=clamp(float(payload.get("denoise", 0.35)), 0.05, 1.0),
        lora_strength=clamp(float(payload.get("lora_strength", 0.8)), 0.0, 2.0),
        cfg=cfg,
        steps=steps,
        sampler=sampler,
        schedule=schedule,
        scale=scale,
        num_images=num_images,
    )


def ensure_pipeline(model_id: str):
    global CURRENT_MODEL_ID, CURRENT_PIPELINE, CURRENT_LORA_ID, CURRENT_LORA_STRENGTH

    if CURRENT_PIPELINE is not None and CURRENT_MODEL_ID == model_id:
        return CURRENT_PIPELINE

    model = get_config_item("models", model_id)
    model_path = model.get("path")
    if not model_path or not Path(model_path).exists():
        raise FileNotFoundError(f"Model checkpoint not found for '{model_id}': {model_path}")

    if CURRENT_PIPELINE is not None:
        del CURRENT_PIPELINE
        CURRENT_PIPELINE = None
        clear_cuda()

    torch = get_torch()
    diffusers = get_diffusers()
    pipe = diffusers["pipeline"].from_single_file(
        model_path,
        torch_dtype=torch.float16,
        use_safetensors=True,
    )
    pipe.scheduler = make_scheduler(pipe.scheduler.config, "dpmpp_2m", "karras")
    pipe = pipe.to("cuda")

    try:
        pipe.enable_xformers_memory_efficient_attention()
    except Exception:
        pass

    if os.getenv("ENABLE_CPU_OFFLOAD", "false").lower() == "true":
        pipe.enable_model_cpu_offload()

    CURRENT_MODEL_ID = model_id
    CURRENT_PIPELINE = pipe
    CURRENT_LORA_ID = "none"
    CURRENT_LORA_STRENGTH = 0.0
    return pipe


def ensure_lora(pipe, lora_id: str, lora_strength: float) -> None:
    global CURRENT_LORA_ID, CURRENT_LORA_STRENGTH

    if lora_id == "none":
        if CURRENT_LORA_ID != "none":
            pipe.unload_lora_weights()
            CURRENT_LORA_ID = "none"
            CURRENT_LORA_STRENGTH = 0.0
        return

    lora = get_config_item("loras", lora_id)
    lora_path = lora.get("path")
    if not lora_path or not Path(lora_path).exists():
        raise FileNotFoundError(f"LoRA not found for '{lora_id}': {lora_path}")

    if CURRENT_LORA_ID != lora_id:
        if CURRENT_LORA_ID != "none":
            pipe.unload_lora_weights()
        pipe.load_lora_weights(lora_path, adapter_name="default")
        CURRENT_LORA_ID = lora_id
        CURRENT_LORA_STRENGTH = None

    if CURRENT_LORA_STRENGTH != lora_strength:
        pipe.set_adapters(["default"], adapter_weights=[lora_strength])
        CURRENT_LORA_STRENGTH = lora_strength


def make_scheduler(config: Any, sampler: str, schedule: str):
    diffusers = get_diffusers()
    if sampler == "euler_a":
        return diffusers["euler_a_scheduler"].from_config(
            config,
            use_karras_sigmas=schedule == "karras",
        )

    if sampler == "ddim":
        return diffusers["ddim_scheduler"].from_config(config)

    return diffusers["scheduler"].from_config(
        config,
        algorithm_type="sde-dpmsolver++",
        use_karras_sigmas=schedule == "karras",
    )


def decode_image(image_base64: str) -> Image.Image:
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    raw = base64.b64decode(image_base64)
    image = Image.open(io.BytesIO(raw))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def normalize_dimensions(image: Image.Image) -> Image.Image:
    max_side = int(os.getenv("MAX_IMAGE_SIDE", "1536"))
    width, height = image.size

    if max(width, height) > max_side:
        ratio = max_side / max(width, height)
        width = int(width * ratio)
        height = int(height * ratio)

    width = max(64, (width // 8) * 8)
    height = max(64, (height // 8) * 8)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def upscale_if_needed(image: Image.Image, scale: float) -> Image.Image:
    if scale == 1.0:
        return image
    width, height = image.size
    return image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)


def encode_image(image: Image.Image) -> dict[str, Any]:
    output_format = os.getenv("OUTPUT_FORMAT", "PNG").upper()
    if output_format not in {"PNG", "WEBP"}:
        output_format = "PNG"

    buffer = io.BytesIO()
    save_kwargs = {"format": output_format}
    if output_format == "WEBP":
        save_kwargs.update({"quality": 95, "method": 6})
    image.save(buffer, **save_kwargs)

    return {
        "image_base64": base64.b64encode(buffer.getvalue()).decode("utf-8"),
        "width": image.width,
        "height": image.height,
        "format": output_format.lower(),
    }


def build_demo_response(generation_input: GenerationInput, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
    source_image = decode_image(generation_input.image_base64)
    source_image = normalize_dimensions(source_image)
    report_progress(progress_callback, 0.12, f"Demo source normalized to {source_image.width}x{source_image.height}")
    output_images = []

    for index in range(generation_input.num_images):
        base_progress = 0.18 + (index / max(1, generation_input.num_images)) * 0.65
        report_progress(progress_callback, base_progress, f"Demo stylizing image {index + 1}/{generation_input.num_images}")
        time.sleep(0.12)
        result = apply_demo_style(source_image, generation_input, index)
        report_progress(progress_callback, base_progress + 0.18, f"Demo filters applied to image {index + 1}")
        time.sleep(0.08)
        result = upscale_if_needed(result, generation_input.scale)
        output_images.append(encode_image(result))
        report_progress(progress_callback, base_progress + 0.35, f"Demo image {index + 1} encoded")

    report_progress(progress_callback, 1.0, "Demo generation complete")
    return {
        "images": output_images,
        "meta": {
            "model_id": generation_input.model_id,
            "lora_id": generation_input.lora_id,
            "denoise": generation_input.denoise,
            "lora_strength": generation_input.lora_strength,
            "steps": generation_input.steps,
            "scale": generation_input.scale,
            "guidance_scale": generation_input.cfg,
            "sampler": generation_input.sampler,
            "schedule": generation_input.schedule,
            "demo_mode": True,
        },
    }


def apply_demo_style(image: Image.Image, generation_input: GenerationInput, index: int) -> Image.Image:
    denoise = generation_input.denoise
    lora_strength = generation_input.lora_strength
    stylized = image.copy()

    detail_layer = stylized.filter(ImageFilter.DETAIL)
    smooth_layer = stylized.filter(ImageFilter.GaussianBlur(radius=1 + denoise * 4))
    stylized = Image.blend(detail_layer, smooth_layer, min(0.75, denoise * 0.9))

    contrast = 1.0 + denoise * 0.35 + index * 0.05
    color = 1.0 + min(lora_strength, 2.0) * 0.28
    sharpness = 1.0 + denoise * 0.4

    stylized = ImageEnhance.Contrast(stylized).enhance(contrast)
    stylized = ImageEnhance.Color(stylized).enhance(color)
    stylized = ImageEnhance.Sharpness(stylized).enhance(sharpness)

    if index % 2 == 0:
        stylized = ImageOps.posterize(stylized, bits=6)
    else:
        stylized = ImageOps.autocontrast(stylized, cutoff=min(12, int(denoise * 20)))

    if generation_input.lora_id != "none":
        overlay = Image.new("RGB", stylized.size, color=(228, 216 + index * 6, 205))
        stylized = Image.blend(stylized, overlay, min(0.24, 0.08 + lora_strength * 0.08))

    return stylized


def get_config_item(section: str, item_id: str) -> dict[str, Any]:
    config = load_config()
    for item in config.get(section, []):
        if item.get("id") == item_id:
            return item
    raise ValueError(f"Unknown {section[:-1]} id: {item_id}")


def load_config() -> dict[str, Any]:
    global MODEL_CONFIG, MODEL_CONFIG_MTIME_NS

    configured_path = Path(os.getenv("MODEL_CONFIG_PATH", ""))
    config_path = configured_path if configured_path.is_file() else DEFAULT_CONFIG_PATH
    mtime_ns = config_path.stat().st_mtime_ns

    if MODEL_CONFIG is not None and MODEL_CONFIG_MTIME_NS == mtime_ns:
        return MODEL_CONFIG

    with config_path.open("r", encoding="utf-8") as config_file:
        MODEL_CONFIG = json.load(config_file)
    MODEL_CONFIG_MTIME_NS = mtime_ns
    return MODEL_CONFIG


def clear_cuda() -> None:
    torch = get_torch()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def report_progress(progress_callback: ProgressCallback | None, progress: float, message: str) -> None:
    if progress_callback is not None:
        progress_callback(min(max(progress, 0.0), 1.0), message)


def build_step_callback(progress_callback: ProgressCallback | None, base_progress: float, total_images: int, image_index: int, steps: int):
    if progress_callback is None:
        return None

    image_span = 0.55 / max(1, total_images)

    def step_callback(_pipe, step_index, _timestep, _kwargs):
        actual_steps = max(1, int(getattr(_pipe, "num_timesteps", steps)))
        fraction = min(1, (step_index + 1) / actual_steps)
        progress = base_progress + fraction * image_span
        report_progress(progress_callback, progress, f"Image {image_index + 1}/{total_images}: step {step_index + 1}/{actual_steps}")
        return _kwargs

    return step_callback
