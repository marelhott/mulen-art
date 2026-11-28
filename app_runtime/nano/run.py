"""Varianty (siblings of one image) and Koláž (fusion of one to ten images): one job = one model, run on a CPU Modal function.

Port of Mulen Nano's VariantsScreen / CollageScreen run logic. Results go through the studio's job machinery and library
(`image_callback`), like unCLIP.
"""
import io
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .. import core
from ..core import GenerationInput, ProgressCallback, report_progress
from . import models, plans, providers

_CANCEL_CHECK: Callable[[], bool] | None = None
TOTAL_INPUT_BYTES = 2_800_000  # shared by all inputs of one request (JSON and base64 overhead)
MAX_DIMENSION = 1400


_PRE_STAGE: Callable[..., list] | None = None


def set_pre_stage(stage: Callable[..., list] | None) -> None:
    """The Modal job registers how to run the unCLIP pre-stage (a GPU job it queues and waits for)."""
    global _PRE_STAGE
    _PRE_STAGE = stage


def set_cancel_check(check: Callable[[], bool] | None) -> None:
    global _CANCEL_CHECK
    _CANCEL_CHECK = check


def prepare_input(image: Image.Image, target_bytes: int) -> str:
    """Downscale to 1400 px and JPEG-encode under the byte budget, as a data URL (optimizeVariantsInput in Mulen Nano)."""
    image = image.convert("RGB")
    longest = max(image.size)
    if longest > MAX_DIMENSION:
        scale = MAX_DIMENSION / longest
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    quality = 90
    while True:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        if len(buffer.getvalue()) <= target_bytes or quality <= 55:
            break
        quality -= 7
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def load_extra_sources(ids: list[str]) -> list[Image.Image]:
    images = []
    for source_id in ids:
        if not re.fullmatch(r"[0-9a-f]{64}", source_id):
            raise ValueError("Invalid source id")
        path = Path(os.environ.get("OUTPUTS_DIR", "/outputs")) / f"source_{source_id}.png"
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    return images


def _run_tasks(tasks: list[dict[str, Any]], spec: dict[str, Any], progress_callback, on_image, label: str) -> list[str]:
    """Run the provider calls concurrently; images are handed over on the calling thread. Returns the error messages of failed tasks."""
    cancelled = _CANCEL_CHECK
    errors: list[str] = []
    client = providers.new_client()
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(5, len(tasks)))) as pool:
            futures = {pool.submit(providers.generate_image, client, spec["model"], task["prompt"], task["images"], task["aspect"], spec["resolution"], cancelled): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                done += 1
                try:
                    on_image(task, future.result())
                except providers.Cancelled:
                    raise
                except Exception as exc:  # one failed variant must not lose the others
                    errors.append(str(exc))
                report_progress(progress_callback, 0.12 + 0.86 * done / len(tasks), f"{label}: {done}/{len(tasks)}")
    finally:
        client.close()
    return errors


def _finish(results: list, errors: list[str], meta: dict[str, Any], started: float, progress_callback) -> dict[str, Any]:
    if not results:
        raise providers.ProviderError(errors[0] if errors else "Model nevrátil žádné obrázky.")
    meta["generation_and_save_seconds"] = round(time.monotonic() - started, 2)
    if errors:
        meta["failed_variants"] = len(errors)
        meta["failure_detail"] = errors[0]
    report_progress(progress_callback, 1.0, "Hotovo" if not errors else f"Hotovo, {len(errors)} selhalo")
    return {"images": results, "meta": meta}


def _generate(generation_input: GenerationInput, kind: str, progress_callback, image_callback, extra_meta) -> dict[str, Any]:
    started = time.monotonic()
    spec = models.BY_ID[generation_input.nano_model]
    title = "Vari" if kind == "vari" else "Koláž"
    report_progress(progress_callback, 0.04, f"Příprava vstupů · {spec['title']}")
    primary = core.decode_image(generation_input.image_base64)
    total_inputs = 1 + (len(generation_input.extra_source_ids) if kind == "collage" else 0)
    fuse = kind == "collage" and generation_input.collage_fuse and total_inputs > 1
    used = total_inputs if fuse else 1
    problem = models.input_error(spec, used)
    if problem:  # before reading any stored source
        raise ValueError(problem)
    sources = [primary]
    if kind == "collage":
        sources += load_extra_sources(generation_input.extra_source_ids)
    budget = TOTAL_INPUT_BYTES // max(1, used)
    count = max(1, min(models.MAX_PER_MODEL, generation_input.num_images))
    seed = generation_input.seed if generation_input.seed >= 0 else random.randrange(1000)
    custom = generation_input.prompt

    tasks: list[dict[str, Any]] = []
    if kind == "vari":
        if generation_input.pre_unclip:
            if _PRE_STAGE is None:
                raise ValueError("unCLIP před Posunem tu není k dispozici.")
            report_progress(progress_callback, 0.06, "unCLIP: příprava mezikroku")
            middles = _PRE_STAGE(primary, generation_input.pre_unclip, count, progress_callback)
            if not middles:
                raise providers.ProviderError("unCLIP nevrátil žádný obrázek.")
            sources_for_variants = [prepare_input(middles[index % len(middles)], budget) for index in range(count)]
        else:
            sources_for_variants = [prepare_input(primary, budget)] * count
        for index in range(count):
            data = sources_for_variants[index]
            tasks.append({"index": index, "images": [data], "aspect": None,
                          "prompt": plans.build_prompt_for_model(spec["model"], custom, generation_input.nano_distance, index)})
    elif fuse:
        shift, prompt = plans.build_fuse_prompt(spec["model"], custom, seed, len(sources))
        encoded = plans.rotate_inputs([prepare_input(image, budget) for image in sources], shift)
        tasks.append({"index": 0, "images": encoded, "aspect": plans.nearest_aspect_ratio(*sources[0].size), "prompt": prompt})
    else:
        data = prepare_input(primary, budget)
        for index in range(count):
            tasks.append({"index": index, "images": [data], "aspect": None,
                          "prompt": plans.build_single_source_prompt(custom, plans.pick_technique(seed + index))})
    report_progress(progress_callback, 0.12, "Vstupy připraveny, generuji")

    meta = {"generation_type": kind, "nano_model": spec["id"], "nano_distance": generation_input.nano_distance, "model_id": f"nano_{spec['id']}",
            "model_name": f"{title} · {spec['title']}", "lora_id": "none", "provider": models.provider_of(spec), "provider_model": spec["model"],
            "prompt": tasks[0]["prompt"], "negative_prompt": "", "scale": 1.0, "demo_mode": False, "source_width": primary.width,
            "source_height": primary.height, "collage_fuse": fuse, "source_count": len(sources),
            # The other inputs of a fused collage: "repeat" brings them back and the source purge keeps their files.
            **({"extra_source_urls": [f"/library/source_{item}.png" for item in generation_input.extra_source_ids]} if len(sources) > 1 else {}),
            "custom_prompt": custom.strip(), "pre_unclip": generation_input.pre_unclip}
    results: list = []

    def on_image(task, data: bytes):
        image = Image.open(io.BytesIO(data))
        image.load()
        image_meta = {**meta, "prompt": task["prompt"], "output_width": image.width, "output_height": image.height, "variant_index": task["index"],
                      "generation_and_save_seconds": round(time.monotonic() - started, 2), **(extra_meta or {})}
        results.append({**core.encode_image(image, image_meta), "generation_meta": image_meta})
        if image_callback is not None:
            image_callback(results[-1], image_meta)

    errors = _run_tasks(tasks, spec, progress_callback, on_image, spec["title"])
    return _finish(results, errors, meta, started, progress_callback)


def generate_variants(generation_input, progress_callback=None, image_callback=None, extra_meta=None):
    return _generate(generation_input, "vari", progress_callback, image_callback, extra_meta)


def generate_collage(generation_input, progress_callback=None, image_callback=None, extra_meta=None):
    return _generate(generation_input, "collage", progress_callback, image_callback, extra_meta)
