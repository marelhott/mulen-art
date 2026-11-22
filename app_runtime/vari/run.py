"""Vari generation: one job = one engine, one distance, up to 12 images, run on a CPU Modal function.

Port of Vari/app/api/generate/route.ts. The studio's job machinery (progress, partial images, library) is reused:
`generate_variations` returns the same shape as app_runtime.unclip, and every image goes through `image_callback`.
"""
import io
import time
from typing import Any, Callable

from PIL import Image, ImageFilter

from .. import core
from ..core import GenerationInput, ProgressCallback, report_progress
from . import catalog, providers

_CANCEL_CHECK: Callable[[], bool] | None = None


def set_cancel_check(check: Callable[[], bool] | None) -> None:
    """The Modal job registers its cancel flag here, so a cancelled job stops polling the provider."""
    global _CANCEL_CHECK
    _CANCEL_CHECK = check


def square_reference(image: Image.Image) -> Image.Image:
    """The square IP-Adapter reference of the Comfy engine: the picture contained on a blurred, dimmed copy of itself."""
    square = max(image.width, image.height)
    background = image.resize((square, square), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(18))
    from PIL import ImageEnhance
    background = ImageEnhance.Brightness(ImageEnhance.Color(background).enhance(0.92)).enhance(0.9)
    foreground = Image.new("RGB", (square, square), (12, 12, 12))
    scale = min(square / image.width, square / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    foreground.paste(resized, ((square - resized.width) // 2, (square - resized.height) // 2))
    background.paste(foreground)
    return background


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _vision_remix_payload(source_url: str, distance: str, prompt: str, info: dict[str, Any], count: int) -> dict[str, Any]:
    size = catalog.snapped_dimensions(info, 1344)
    pick = lambda values: catalog._by_distance(distance, values)  # noqa: E731
    return {"_model_id": "fal-ai/fast-sdxl/image-to-image", "image_url": source_url, "prompt": prompt,
            "negative_prompt": "exact duplicate, same framing, same crop, same composition, polished stock photo, glossy render, generic concept art, vectorized simplification, poster design",
            "num_images": max(1, min(4, count)), "image_size": size,
            "num_inference_steps": pick((40, 36, 32, 28)), "guidance_scale": pick((3.6, 3.2, 2.9, 2.6)),
            "strength": pick((0.42, 0.52, 0.64, 0.76)), "expand_prompt": False, "enable_safety_checker": False, "format": "png"}


def generate_variations(generation_input: GenerationInput, progress_callback: ProgressCallback | None = None,
                        image_callback: Callable | None = None, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    engine, distance, count = generation_input.vari_engine, generation_input.vari_distance, generation_input.num_images
    spec = catalog.ENGINES[engine]
    report_progress(progress_callback, 0.04, f"Příprava zdroje · {spec['label']}")
    source = core.decode_image(generation_input.image_base64)
    source_png = png_bytes(source)
    info = catalog.image_info(source.width, source.height)
    cancelled = _CANCEL_CHECK
    client = providers.new_client()
    try:
        source_url = providers.fal_upload(client, source_png)
        report_progress(progress_callback, 0.12, "Zdroj nahrán")
        outputs: list[bytes] = []
        prompt = negative = ""

        if engine in ("gpt-image-2", "gemini-3-pro"):
            analysis = providers.analyze_image_for_variant(client, source_url)
            prompt = catalog.build_gpt_image2_prompt(distance, analysis)
            report_progress(progress_callback, 0.3, "Analýza obrazu hotová, generuji")
            n = max(1, min(4, count))
            if engine == "gpt-image-2":
                size = "1024x1024" if info["width"] == info["height"] else "1536x1024" if info["width"] > info["height"] else "1024x1536"
                outputs = providers.edit_with_gpt_image2(client, source_png, prompt, n, size)
            else:
                outputs = providers.edit_with_gemini_3_pro(client, source_png, prompt, n, info["width"], info["height"])
        else:
            if engine == "vision-remix":
                analysis = providers.analyze_image_for_variant(client, source_url)
                prompt = catalog.build_vision_remix_prompt(distance, analysis)
                report_progress(progress_callback, 0.3, "Analýza obrazu hotová, generuji")
                payload = _vision_remix_payload(source_url, distance, prompt, info, count)
            else:
                ctx: dict[str, Any] = {"source_url": source_url, "image_info": info, "distance": distance, "count": count,
                                       **generation_input.vari_tuning}
                if engine == "comfy-unclip":
                    ctx["comfy_reference_url"] = providers.fal_upload(client, png_bytes(square_reference(source)))
                payload = catalog.build_payload(engine, ctx)
                prompt, negative = payload.get("prompt", ""), payload.get("negative_prompt", "")
            if payload.get("_provider") == "replicate":
                images = providers.run_replicate(client, payload, cancelled=cancelled,
                                                 on_status=lambda status: report_progress(progress_callback, 0.5, f"Replicate: {status}"))
            else:
                images = providers.run_fal(client, payload, cancelled=cancelled)
            report_progress(progress_callback, 0.8, "Stahuji výsledky")
            outputs = [providers.download(client, item["url"]) for item in images if item.get("url")]
        if not outputs:
            raise providers.ProviderError(f"{spec['label']} nevrátil žádné obrázky.")
        meta = {"generation_type": "vari", "vari_engine": engine, "vari_distance": distance, "model_id": f"vari_{engine}",
                "model_name": f"Vari · {spec['label']}", "lora_id": "none", "provider": spec["provider"],
                "prompt": prompt, "negative_prompt": negative, "scale": 1.0, "demo_mode": False,
                "tuning": generation_input.vari_tuning, "source_width": source.width, "source_height": source.height}
        results = []
        for index, data in enumerate(outputs):
            image = Image.open(io.BytesIO(data))
            image.load()
            image_meta = {**meta, "output_width": image.width, "output_height": image.height, "variant_index": index,
                          "generation_and_save_seconds": round(time.monotonic() - started, 2), **(extra_meta or {})}
            results.append({**core.encode_image(image, image_meta), "generation_meta": image_meta})
            if image_callback is not None:
                image_callback(results[-1], image_meta)
            report_progress(progress_callback, 0.8 + 0.18 * (index + 1) / len(outputs), f"Uloženo {index + 1}/{len(outputs)}")
        meta["generation_and_save_seconds"] = round(time.monotonic() - started, 2)
        report_progress(progress_callback, 1.0, "Hotovo")
        return {"images": results, "meta": meta}
    finally:
        client.close()
