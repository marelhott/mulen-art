"""Reimagine: image variations with Stable Diffusion 2.1 unCLIP (the model behind Clipdrop's old Reimagine).

The pipeline conditions on the CLIP embedding of the source image, so it needs no prompt. Weights are
downloaded once with scripts/download_unclip.py into /models/unclip on the models Volume.
"""
import os
import random
import time
from pathlib import Path
from typing import Any, Callable

from . import core
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


def generate_variations(generation_input: GenerationInput, progress_callback: ProgressCallback | None = None,
                        image_callback: Callable | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    torch = core.get_torch()
    report_progress(progress_callback, 0.06, "Loading SD 2.1 unCLIP")
    pipe = ensure_unclip_pipeline()
    report_progress(progress_callback, 0.18, "Model ready: SD 2.1 unCLIP")
    source = core.decode_image(generation_input.image_base64)
    width, height = output_size(source.width, source.height)
    source = source.resize((width, height))
    setup_seconds = time.monotonic() - started
    total = generation_input.num_images
    meta = {
        "generation_type": "reimagine", "model_id": UNCLIP_MODEL_ID, "model_name": UNCLIP_MODEL_NAME, "lora_id": "none",
        "noise_level": generation_input.noise_level, "denoise": generation_input.denoise, "steps": generation_input.steps, "guidance_scale": generation_input.cfg,
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
        image_meta = {**meta, "seed": seed, "actual_steps": run_steps,
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
