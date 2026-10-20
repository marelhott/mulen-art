"""Private autonomous studies. Starter subjects are curated, not an archive analysis."""
import random

SUBJECTS = [
    ("face", "Část tváře mimo záběr", "a tightly cropped face, one eye outside the frame, neutral expression"),
    ("face", "Tvář z nekvalitního záznamu", "a face seen in a low quality television still, indistinct expression, plain background"),
    ("face", "Zátylek", "the back of a head, cropped shoulders, no surrounding context"),
    ("face", "Průkazový portrét", "an enlarged small identification photograph, frontal head, flat light"),
    ("interior", "Výřez chodby", "a cropped institutional corridor, a closed door partly outside the frame, flat daylight"),
    ("interior", "Stěna a okraj okna", "a plain wall and the edge of a window, no view outside, subdued daylight"),
    ("interior", "Prázdná místnost", "an unoccupied ordinary room, partial furniture at the frame edge, flat light"),
    ("interior", "Zábradlí", "a close cropped section of a staircase railing, no people, even daylight"),
    ("object", "Detail rukávu", "a cropped sleeve and part of a hand, ordinary fabric, plain background"),
    ("object", "Předmět v obalu", "a small ordinary object partly covered by plain wrapping, close cropped view"),
    ("object", "Pohár na stole", "the upper half of a plain drinking glass on a table, cropped view, flat light"),
    ("object", "Přeložená látka", "a close cropped piece of folded plain cloth, a few broad folds"),
    ("landscape", "Okraj stavby", "part of a low ordinary building at the edge of the frame, empty pale sky"),
    ("landscape", "Výřez vegetace", "a tightly cropped patch of ordinary foliage against a flat wall"),
    ("landscape", "Vzdálený břeh", "a distant bank across a narrow strip of water, flat overcast light"),
    ("landscape", "Část hřiště", "an empty cropped section of a sports field, a faint line across the ground"),
    ("figure", "Postava zezadu", "a distant ordinary person seen from behind, cropped setting, no visible action"),
    ("figure", "Část skupiny", "a cropped portion of an ordinary group photograph, partial shoulders and faces"),
    ("figure", "Sedící postava", "an ordinary seated person, hands partly outside the frame, neutral background"),
    ("figure", "Gesto ruky", "a close cropped hand resting against ordinary clothing, no visible face"),
]
THEMES = {"all", "face", "interior", "object", "landscape", "figure"}
MODES = {"noise", "subject", "photo", "archive"}


def is_atelier_model(model_id):
    return model_id.startswith("tuymans_") or model_id in {"tuy_small", "hofmann_sdxl"}


def subject_for(seed, theme="all"):
    choices = [(i, item) for i, item in enumerate(SUBJECTS) if theme == "all" or item[0] == theme]
    index, (_, title, text) = random.Random(seed).choice(choices)
    return index, title, text


def painting_prompt(model_id, text):
    # Keep the learned caption prefix for the approved checkpoints; no descriptive style embellishment.
    if model_id == "hofmann_sdxl":
        return text  # No verified caption trigger is available for this imported checkpoint.
    trigger = "mvhpaint" if model_id.startswith("tuymans_modal_") else "tuypaint"
    return f"{trigger}, {text}"


def generate_study(spec, progress, image_callback):
    if spec.atelier_mode == "archive":
        from .archives import generate_reference
        return generate_reference(spec, progress, image_callback)
    import time
    from . import core
    started = time.monotonic()
    torch = core.get_torch()
    modules = core.get_diffusers()
    output_images = []
    last_meta = {}
    for index in range(spec.num_images):
        seed = random.randint(0, 2**32 - 1) if spec.seed == -1 else (spec.seed + index) % 2**32
        subject_id, title, text = subject_for(seed, spec.atelier_theme)
        if spec.atelier_mode == "noise":
            title, text, subject_id = "Volná studie bez námětu", "", None
        base = index / spec.num_images
        span = 1 / spec.num_images
        def notify(value, message):
            core.report_progress(progress, .02 + .98 * (base + value * span), message)
        def generator():
            return torch.Generator(device="cuda").manual_seed(seed)
        prompt = "" if spec.atelier_mode == "noise" else painting_prompt(spec.model_id, text)
        notify(.02, "Ateliér: načítání modelu")
        source_url = None
        # The optional photographic study uses SDXL Base, then releases its pipeline before painting.
        if spec.atelier_mode == "photo":
            pipe = core.ensure_pipeline("sdxl_base")
            core.ensure_lora(pipe, "none", 0)
            pipe.scheduler = core.make_scheduler(pipe.scheduler.config, spec.sampler, spec.schedule)
            text_pipe = modules["text_pipeline"].from_pipe(pipe)
            photo_prompt = f"An ordinary documentary photograph of {text}. Flat light, no dramatic lighting."
            notify(.12, "Ateliér: vytváření fotografické předlohy")
            photo = text_pipe(prompt=photo_prompt, negative_prompt=None, width=spec.width, height=spec.height,
                guidance_scale=spec.cfg, num_inference_steps=spec.steps, generator=generator(),
                callback_on_step_end=core.build_step_callback(notify, .12, 1, 0, spec.steps, span=.30, stage="Předloha"),
                callback_on_step_end_tensor_inputs=[]).images[0]
            del text_pipe, pipe
            # Persist the actual generated source for the comparison viewer and audit trail.
            import hashlib, io
            from .server import OUTPUTS_DIR
            buffer = io.BytesIO(); photo.save(buffer, format="PNG"); data = buffer.getvalue()
            filename = "source_atelier_" + hashlib.sha256(data).hexdigest() + ".png"
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUTS_DIR / filename).write_bytes(data)
            source_url = f"/library/{filename}"
            notify(.45, "Ateliér: přemalování vlastním checkpointem")
            pipe = core.ensure_pipeline(spec.model_id)
            core.ensure_lora(pipe, "none", 0)
            pipe.scheduler = core.make_scheduler(pipe.scheduler.config, spec.sampler, spec.schedule)
            result = pipe(prompt="", negative_prompt=None, image=photo, strength=spec.denoise,
                guidance_scale=spec.cfg, num_inference_steps=spec.steps, generator=generator(),
                callback_on_step_end=core.build_step_callback(notify, .50, 1, 0, spec.steps, span=.40, stage="Malba"),
                callback_on_step_end_tensor_inputs=[]).images[0]
            actual_steps = int(pipe.num_timesteps)
            prompt = ""
        else:
            pipe = core.ensure_pipeline(spec.model_id)
            core.ensure_lora(pipe, "none", 0)
            pipe.scheduler = core.make_scheduler(pipe.scheduler.config, spec.sampler, spec.schedule)
            text_pipe = modules["text_pipeline"].from_pipe(pipe)
            notify(.15, "Ateliér: nový obraz z šumu")
            result = text_pipe(prompt=prompt, negative_prompt=None, width=spec.width, height=spec.height,
                guidance_scale=spec.cfg, num_inference_steps=spec.steps, generator=generator(),
                callback_on_step_end=core.build_step_callback(notify, .18, 1, 0, spec.steps, span=.72, stage="Ateliér"),
                callback_on_step_end_tensor_inputs=[]).images[0]
            actual_steps = int(text_pipe.num_timesteps)
            del text_pipe
        result = core.upscale_if_needed(result, spec.scale)
        meta = {"generation_type": "atelier", "atelier_mode": spec.atelier_mode,
            "atelier_theme": spec.atelier_theme, "subject_id": subject_id, "subject_title": title,
            "subject_text": text, "subject_origin": "none" if subject_id is None else "curated-starter-v1",
            "model_id": spec.model_id, "model_name": core.get_config_item("models", spec.model_id)["name"],
            "lora_id": "none", "seed": seed, "steps": spec.steps, "actual_steps": actual_steps,
            "guidance_scale": spec.cfg, "cfg": spec.cfg, "sampler": spec.sampler, "schedule": spec.schedule,
            "generation_width": spec.width, "generation_height": spec.height,
            "output_width": result.width, "output_height": result.height,
            "scale": spec.scale, "upscaler": "lanczos", "render_mode": "quick",
            "prompt": prompt, "negative_prompt": "", "denoise": spec.denoise if spec.atelier_mode == "photo" else None,
            "source_url": source_url, "source_name": title, "demo_mode": False,
            "photo_prompt": photo_prompt if spec.atelier_mode == "photo" else None,
            "photo_model_id": "sdxl_base" if spec.atelier_mode == "photo" else None,
            "generation_and_save_seconds": round(time.monotonic() - started, 2)}
        image = {**core.encode_image(result, meta), "generation_meta": meta}
        output_images.append(image)
        if image_callback: image_callback(image, meta)
        last_meta = meta
        notify(1, "Ateliér: obraz uložen")
    return {"images": output_images, "meta": last_meta}
