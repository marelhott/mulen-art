"""Reimagine: image variations with Stable Diffusion 2.1 unCLIP (the model behind Clipdrop's old Reimagine).

The pipeline conditions on the CLIP embedding of the source image, so it needs no prompt. Weights are
downloaded once with scripts/download_unclip.py into /models/unclip on the models Volume.
"""
import os
import random
import time
from pathlib import Path
from typing import Any, Callable

from . import core, glitch
from .core import GenerationInput, ProgressCallback, report_progress

UNCLIP_MODEL_ID = "sd21_unclip"
UNCLIP_MODEL_NAME = "SD 2.1 unCLIP (Reimagine)"
UNCLIP_NATIVE_SIDE = 768  # the "H" model is trained at 768x768
_PIPELINE: dict[str, Any] = {}


def unclip_dir() -> Path:
    return Path(os.getenv("UNCLIP_DIR", "/models/unclip"))


def output_size(width: int, height: int, native: int = UNCLIP_NATIVE_SIDE) -> tuple[int, int]:
    """Keep the source aspect ratio with the longer side at the native size; both sides multiples of 8."""
    scale = native / max(width, height)
    return (max(256, round(width * scale / 8) * 8), max(256, round(height * scale / 8) * 8))


def ensure_unclip_pipeline():
    if "pipe" in _PIPELINE:
        return _PIPELINE["pipe"]
    path = unclip_dir()
    if not (path / "model_index.json").is_file():
        raise RuntimeError("SD 2.1 unCLIP weights are missing; run: .venv/bin/python -m modal run scripts/download_unclip.py")
    torch = core.get_torch()
    from diffusers import DDIMScheduler, StableUnCLIPImg2ImgPipeline
    pipe = StableUnCLIPImg2ImgPipeline.from_pretrained(path, torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    # DDIM can start part-way through the schedule, which is what keeps the source's composition (see prepare_init_latents).
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    try:
        pipe.vae.enable_tiling()
    except Exception:
        pass
    _PIPELINE["pipe"] = pipe
    return pipe


def embedding_image(source):
    """The whole picture for the CLIP encoder. Its processor centre-crops to a square, so a portrait or landscape
    source would otherwise be judged by a middle strip only; squashing to a square keeps every part of it."""
    return source.resize((UNCLIP_NATIVE_SIDE, UNCLIP_NATIVE_SIDE))


def start_index(steps: int, strength: float) -> int:
    """First schedule step that is run: strength 1 runs all of them (pure noise), 0.6 the last 60 %."""
    return min(steps - 1, max(0, int(steps * (1.0 - strength))))


def prepare_init_latents(pipe, source, strength: float, steps: int, generator, torch):
    """Noised latents of the source plus the schedule index to start from (img2img around the unCLIP embedding).

    Returns (None, 0) for strength >= 0.99: the old behaviour, a variation generated from pure noise."""
    if strength >= 0.99:
        return None, 0
    import numpy as np
    pipe.scheduler.set_timesteps(steps, device="cuda")
    begin = start_index(steps, strength)
    pixels = torch.from_numpy(np.asarray(source, dtype=np.float32) / 127.5 - 1.0).permute(2, 0, 1)[None]
    pixels = pixels.to(device="cuda", dtype=pipe.vae.dtype)
    with torch.no_grad():
        latents = pipe.vae.encode(pixels).latent_dist.sample(generator) * pipe.vae.config.scaling_factor
    noise = torch.randn(latents.shape, generator=generator, device="cuda", dtype=latents.dtype)
    timestep = pipe.scheduler.timesteps[begin:begin + 1]
    return pipe.scheduler.add_noise(latents, noise, timestep), begin


def step_callback(progress_callback, base: float, span: float, index: int, total: int, steps: int):
    """unCLIP in diffusers 0.32 still uses the legacy `callback(step, timestep, latents)` API (no callback_on_step_end)."""
    if progress_callback is None:
        return None

    def callback(step_index, _timestep, _latents):
        fraction = min(1.0, (step_index + 1) / max(1, steps))
        report_progress(progress_callback, base + fraction * span, f"Variation {index + 1}/{total}: step {min(step_index + 1, steps)}/{steps}")

    return callback


METAMORPH_MODEL_NAME = "SDXL Base + IP-Adapter (Metamorfóza)"
IP_ADAPTER_WEIGHTS = {"plain": "ip-adapter_sdxl_vit-h.safetensors", "plus": "ip-adapter-plus_sdxl_vit-h.safetensors"}


def ipadapter_dir() -> Path:
    return Path(os.getenv("IPADAPTER_DIR", "/models/ipadapter"))


def metamorph_size(width: int, height: int, pixels: int = 1024 * 1024) -> tuple[int, int]:
    """About one megapixel (SDXL's native area) with the source's aspect ratio; both sides multiples of 64."""
    ratio = width / height
    return (max(512, round((pixels * ratio) ** 0.5 / 64) * 64), max(512, round((pixels / ratio) ** 0.5 / 64) * 64))


def ensure_metamorph_pipeline():
    """SDXL Base img2img with both ViT-H IP-Adapters loaded. Its own instance: core.PIPELINES must never see the adapters,
    or the user's normal SDXL Base + LoRA jobs would be silently conditioned on an image."""
    if "metamorph" in _PIPELINE:
        return _PIPELINE["metamorph"]
    base = core.get_config_item("models", "sdxl_base")["path"]
    adapters = ipadapter_dir()
    missing = [str(path) for path in (Path(base), adapters / "models/image_encoder/model.safetensors",
               *(adapters / "sdxl_models" / name for name in IP_ADAPTER_WEIGHTS.values())) if not path.is_file()]
    if missing:
        raise RuntimeError("Metamorfóza is missing weights (" + ", ".join(missing) + "); run scripts/download_sdxl_base.py and scripts/download_ipadapter.py")
    torch = core.get_torch()
    from diffusers import StableDiffusionXLImg2ImgPipeline
    pipe = StableDiffusionXLImg2ImgPipeline.from_single_file(base, torch_dtype=torch.float16, use_safetensors=True)
    pipe.scheduler = core.make_scheduler(pipe.scheduler.config, "dpmpp_2m", "karras")
    # Both adapters share the ViT-H encoder; each request switches one on through its scale. No xformers afterwards:
    # enabling it would replace the IP-Adapter attention processors and the source image would stop having any effect.
    pipe.load_ip_adapter(str(adapters), subfolder="sdxl_models", weight_name=list(IP_ADAPTER_WEIGHTS.values()),
                         image_encoder_folder="models/image_encoder")
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    pipe.enable_vae_tiling()
    _PIPELINE["metamorph"] = pipe
    return pipe


def adapter_scales(variant: str, scale: float) -> list[float]:
    return [scale if name == variant else 0.0 for name in IP_ADAPTER_WEIGHTS]


def generate_metamorph(generation_input: GenerationInput, progress_callback: ProgressCallback | None = None,
                       image_callback: Callable | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reimagine XL style: SDXL starts from the noised source (keeps layout, palette, gesture) while the IP-Adapter feeds
    it the picture's content and style, so the forms are re-invented rather than copied."""
    started = time.monotonic()
    torch = core.get_torch()
    report_progress(progress_callback, 0.06, "Loading SDXL Base + IP-Adapter")
    pipe = ensure_metamorph_pipeline()
    report_progress(progress_callback, 0.18, "Model ready: Metamorfóza")
    source = core.decode_image(generation_input.image_base64)
    width, height = metamorph_size(source.width, source.height)
    source = source.resize((width, height))
    reference = embedding_image(source)
    pipe.set_ip_adapter_scale(adapter_scales(generation_input.ip_variant, generation_input.ip_scale))
    setup_seconds = time.monotonic() - started
    total = generation_input.num_images
    meta = {
        "generation_type": "reimagine", "reimagine_mode": "metamorph", "model_id": UNCLIP_MODEL_ID, "model_name": METAMORPH_MODEL_NAME,
        "lora_id": "none", "denoise": generation_input.denoise, "ip_scale": generation_input.ip_scale, "ip_variant": generation_input.ip_variant,
        "steps": generation_input.steps, "guidance_scale": generation_input.cfg, "sampler": "dpmpp_2m", "schedule": "karras",
        "prompt": generation_input.prompt, "negative_prompt": generation_input.negative_prompt,
        "scale": 1.0, "demo_mode": False, "recipe": core.runtime_recipe(pipe),
        "generation_width": width, "generation_height": height,
    }
    output_images = []
    inference_started = time.monotonic()
    for index in range(total):
        seed = random.randint(0, 2**32 - 1) if generation_input.seed == -1 else (generation_input.seed + index) % 2**32
        generator = torch.Generator(device="cuda").manual_seed(seed)
        base = 0.22 + (index / total) * 0.76
        report_progress(progress_callback, base, f"Variation {index + 1}/{total}")
        result = pipe(
            prompt=generation_input.prompt, negative_prompt=generation_input.negative_prompt,
            image=source, strength=generation_input.denoise,
            ip_adapter_image=[reference] * len(IP_ADAPTER_WEIGHTS),
            num_inference_steps=generation_input.steps, guidance_scale=generation_input.cfg,
            generator=generator,
            callback_on_step_end=core.build_step_callback(progress_callback, base, total, index, generation_input.steps, span=0.76 / total),
            callback_on_step_end_tensor_inputs=[],
        ).images[0]
        image_meta = {**meta, "seed": seed, "actual_steps": int(pipe.num_timesteps),
                      "output_width": result.width, "output_height": result.height,
                      "setup_seconds": round(setup_seconds, 2),
                      "generation_and_save_seconds": round(time.monotonic() - inference_started, 2),
                      **(extra_meta or {})}
        output_images.append({**core.encode_image(result, image_meta), "generation_meta": image_meta})
        if image_callback is not None:
            image_callback(output_images[-1], image_meta)
        meta.update(image_meta)
        report_progress(progress_callback, base + 0.76 / total, f"Variation {index + 1}/{total} saved")
    meta["setup_seconds"] = round(setup_seconds, 2)
    meta["generation_and_save_seconds"] = round(time.monotonic() - inference_started, 2)
    report_progress(progress_callback, 1.0, "Generation complete")
    return {"images": output_images, "meta": meta}


def generate_variations(generation_input: GenerationInput, progress_callback: ProgressCallback | None = None,
                        image_callback: Callable | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    if generation_input.reimagine_mode == "metamorph":
        return generate_metamorph(generation_input, progress_callback, image_callback, extra_meta)
    started = time.monotonic()
    torch = core.get_torch()
    report_progress(progress_callback, 0.06, "Loading SD 2.1 unCLIP")
    pipe = ensure_unclip_pipeline()
    report_progress(progress_callback, 0.18, "Model ready: SD 2.1 unCLIP")
    source = core.decode_image(generation_input.image_base64)
    width, height = output_size(source.width, source.height, generation_input.long_side)
    source = source.resize((width, height))
    setup_seconds = time.monotonic() - started
    total = generation_input.num_images
    meta = {
        "generation_type": "reimagine", "model_id": UNCLIP_MODEL_ID, "model_name": UNCLIP_MODEL_NAME, "lora_id": "none",
        "reimagine_mode": "unclip", "noise_level": generation_input.noise_level, "denoise": generation_input.denoise, "steps": generation_input.steps, "guidance_scale": generation_input.cfg,
        "prompt": generation_input.prompt, "negative_prompt": generation_input.negative_prompt,
        "scale": 1.0, "demo_mode": False, "recipe": core.runtime_recipe(pipe),
        "generation_width": width, "generation_height": height,
    }
    output_images = []
    inference_started = time.monotonic()
    for index in range(total):
        seed = random.randint(0, 2**32 - 1) if generation_input.seed == -1 else (generation_input.seed + index) % 2**32
        generator = torch.Generator(device="cuda").manual_seed(seed)
        base = 0.22 + (index / total) * 0.76
        report_progress(progress_callback, base, f"Variation {index + 1}/{total}")
        init_latents, begin = prepare_init_latents(pipe, source, generation_input.denoise, generation_input.steps, generator, torch)
        run_steps = generation_input.steps - begin
        original_set_timesteps = pipe.scheduler.set_timesteps

        def set_timesteps_from(count, device=None, _begin=begin):
            original_set_timesteps(count, device=device)
            pipe.scheduler.timesteps = pipe.scheduler.timesteps[_begin:]

        pipe.scheduler.set_timesteps = set_timesteps_from
        try:
            with glitch.damaged(pipe, generation_input.glitch, run_steps, generation_input.glitch_until, seed) as glitch_info:
                result = pipe(
                    image=embedding_image(source), latents=init_latents,
                    prompt=generation_input.prompt or None,
                    negative_prompt=generation_input.negative_prompt or None,
                    width=width, height=height,
                    num_inference_steps=generation_input.steps,
                    guidance_scale=generation_input.cfg,
                    noise_level=generation_input.noise_level,
                    generator=generator,
                    callback=step_callback(progress_callback, base, 0.76 / total, index, total, run_steps),
                    callback_steps=1,
                ).images[0]
        finally:
            pipe.scheduler.set_timesteps = original_set_timesteps
        image_meta = {**meta, "seed": seed, "actual_steps": run_steps, **({"glitch": glitch_info["glitch"], "glitch_until": generation_input.glitch_until} if glitch_info["glitch"] else {}),
                      "output_width": result.width, "output_height": result.height,
                      "setup_seconds": round(setup_seconds, 2),
                      "generation_and_save_seconds": round(time.monotonic() - inference_started, 2),
                      **(extra_meta or {})}
        output_images.append({**core.encode_image(result, image_meta), "generation_meta": image_meta})
        if image_callback is not None:
            image_callback(output_images[-1], image_meta)
        meta.update(image_meta)
        report_progress(progress_callback, base + 0.76 / total, f"Variation {index + 1}/{total} saved")
    meta["setup_seconds"] = round(setup_seconds, 2)
    meta["generation_and_save_seconds"] = round(time.monotonic() - inference_started, 2)
    report_progress(progress_callback, 1.0, "Generation complete")
    return {"images": output_images, "meta": meta}
