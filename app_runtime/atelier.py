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
    if model_id.startswith("mix:"):
        from .core import parse_mix_id
        return all(is_atelier_model(part_id) for part_id, _ in parse_mix_id(model_id))
    return model_id.startswith("tuymans_") or model_id in {"tuy_small", "hofmann_sdxl", "mulen_mara"}


def subject_for(seed, theme="all"):
    choices = [(i, item) for i, item in enumerate(SUBJECTS) if theme == "all" or item[0] == theme]
    index, (_, title, text) = random.Random(seed).choice(choices)
    return index, title, text


def painting_prompt(model_id, text):
    if model_id.startswith("mix:"):  # every trained component contributes its learned caption prefix
        from .core import parse_mix_id
        triggers = []
        for part_id, _ in parse_mix_id(model_id):
            prefix = painting_prompt(part_id, "").rstrip(", ")
            if prefix and prefix not in triggers:
                triggers.append(prefix)
        return ", ".join(triggers + [text]) if text else ", ".join(triggers)
    # Keep the learned caption prefix for the approved checkpoints; no descriptive style embellishment.
    if model_id == "hofmann_sdxl":
        return text  # No verified caption trigger is available for this imported checkpoint.
    if model_id == "mulen_mara":
        return f"mulpaint, {text}"  # the caption prefix the checkpoint was trained with
    trigger = "mvhpaint" if model_id.startswith("tuymans_modal_") else "tuypaint"
    return f"{trigger}, {text}"


# Colour. Sampled from pure noise with an empty prompt, a fine-tuned checkpoint falls to one average palette
# (measured: ~98 % of "Volná studie" outputs share the same dominant hue, while the artists' paintings vary
# widely). Biasing the start latent cannot fix that without destroying the painting (any offset makes the
# model draw a flat field). What does work, because the training captions contained colour words, is a short
# colour hint - never a subject - at a guidance scale where text acts: "pale blue and grey". The hint is
# derived from the dominant colours of a random real painting of the same artist, so palettes follow the
# artist's actual distribution.
COLOR_GUIDANCE_VIVID = 4.5  # level 2: stronger text pull, no "muted/pale" qualifiers
COLOR_GUIDANCE = 3.0  # lowest CFG at which the colour hint reliably shows (0.5 ignores text entirely)
COLOR_ARCHIVES = {"hofmann_sdxl": "hofmann", "mulen_mara": "mulen"}
FALLBACK_COLORS = ["red", "pink", "orange", "yellow", "green", "teal", "blue", "violet", "brown", "grey", "white", "black"]


def color_archive_for(model_id):
    if model_id.startswith("mix:"):
        from .core import parse_mix_id
        return color_archive_for(parse_mix_id(model_id)[0][0])
    if model_id in COLOR_ARCHIVES:
        return COLOR_ARCHIVES[model_id]
    return "tuymans" if model_id.startswith("tuymans_") or model_id == "tuy_small" else None


def color_name(hue, saturation, value):
    """Name of one pixel's colour: about 35 shades, so palettes are not limited to a dozen basic colours."""
    h, s_, v = hue % 1.0, saturation, value
    if v < 0.2:
        return "black"
    if s_ < 0.12:
        return "white" if v > 0.85 else ("light grey" if v > 0.62 else ("grey" if v > 0.36 else "charcoal"))
    if h >= 0.95 or h < 0.03:
        return "burgundy" if v < 0.42 else ("pink" if (v > 0.7 and s_ < 0.5) else "red")
    if h < 0.07:
        return "rust" if v < 0.6 else ("salmon" if (s_ < 0.5 and v > 0.7) else "coral")
    if h < 0.11:
        if v < 0.5:
            return "brown"
        if s_ < 0.35:
            return "beige"
        return "terracotta" if v < 0.65 else ("peach" if s_ < 0.55 else "orange")
    if h < 0.17:
        if s_ < 0.3 and v > 0.8:
            return "cream"
        return "ochre" if v < 0.7 else "yellow"
    if h < 0.25:
        return "olive" if v < 0.55 else ("sage" if s_ < 0.4 else "lime")
    if h < 0.42:
        return "sage" if s_ < 0.3 else ("dark green" if v < 0.45 else ("mint" if (v > 0.78 and s_ < 0.5) else "green"))
    if h < 0.52:
        return "teal" if v < 0.65 else "turquoise"
    if h < 0.62:
        return "navy" if v < 0.4 else ("sky blue" if (v > 0.75 and s_ < 0.55) else "blue")
    if h < 0.72:
        return "navy" if v < 0.4 else ("slate blue" if s_ < 0.35 else ("cobalt" if s_ > 0.7 else "blue"))
    if h < 0.83:
        return "purple" if v < 0.5 else ("lavender" if (v > 0.7 and s_ < 0.45) else ("mauve" if s_ < 0.3 else "violet"))
    return "plum" if v < 0.5 else ("magenta" if s_ >= 0.6 else "pink")


NEUTRALS = {"white", "light grey", "grey", "charcoal", "black"}
# Only the basic names take a "pale/muted/dark" qualifier; the finer shades (ochre, mauve, navy ...) already encode it.
QUALIFIABLE = {"red", "orange", "yellow", "green", "blue", "violet", "pink", "brown", "teal"}


def color_phrase_from_image(image, adjectives=True):
    """The painting's colour in the captions' vocabulary, e.g. "pale blue and grey".

    Chromatic colours lead (two of them when the second is substantial); a neutral only fills in when the
    painting has one chromatic colour, or is itself almost neutral (about a third of the archive).
    """
    small = image.convert("RGB").resize((48, 48))
    counts, stats = {}, {}
    raw = small.convert("HSV").tobytes()
    for h, s_, v in zip(raw[0::3], raw[1::3], raw[2::3]):
        name = color_name(h / 255, s_ / 255, v / 255)
        counts[name] = counts.get(name, 0) + 1
        agg = stats.setdefault(name, [0.0, 0.0])
        agg[0] += s_ / 255; agg[1] += v / 255
    total = sum(counts.values())
    chromatic = sorted(((n, c) for n, c in counts.items() if n not in NEUTRALS), key=lambda item: -item[1])
    neutral = sorted(((n, c) for n, c in counts.items() if n in NEUTRALS), key=lambda item: -item[1])
    if sum(c for _, c in chromatic) < 0.05 * total:
        ranked = [n for n, _ in neutral[:2]]
    else:
        ranked = [chromatic[0][0]]
        if len(chromatic) > 1 and chromatic[1][1] >= 0.25 * chromatic[0][1]:
            ranked.append(chromatic[1][0])
        elif neutral:
            ranked.append(neutral[0][0])
    parts = []
    for name in ranked:
        sat, val = (stats[name][0] / counts[name], stats[name][1] / counts[name])
        adjective = "" if (name not in QUALIFIABLE or not adjectives) else ("dark" if val < 0.4 else ("pale" if sat < 0.32 and val > 0.7 else ("muted" if sat < 0.35 else "")))
        parts.append(f"{adjective} {name}".strip())
    return " and ".join(parts)


def color_hint(model_id, seed, adjectives=True):
    """(phrase, source) for this study; the source names the archive painting the palette came from."""
    import random as _random
    from PIL import Image, ImageOps
    from .archives import load_manifest, reference_for
    archive_id = color_archive_for(model_id)
    if archive_id and any(a["id"] == archive_id and a.get("items") for a in load_manifest()["archives"]):
        _, item, path = reference_for(archive_id, (seed * 2654435761) % 2**32)
        with Image.open(path) as raw:
            phrase = color_phrase_from_image(ImageOps.exif_transpose(raw), adjectives)
        return phrase, item.get("filename") or item.get("id")
    rng = _random.Random(seed)
    first, second = rng.sample(FALLBACK_COLORS, 2)
    return f"{first} and {second}", None


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
        # Colour hint for the two modes that start from nothing (noise, subject). The photo mode already gets its
        # colours from the photograph and the archive mode from the reference painting.
        base_prompt = prompt
        color_text, color_source, cfg = None, None, spec.cfg
        if spec.atelier_mode in {"noise", "subject"} and (spec.atelier_color_level > 0 or spec.atelier_color_text):
            if spec.atelier_color_text:
                color_text = spec.atelier_color_text
            else:
                color_text, color_source = color_hint(spec.model_id, seed, adjectives=spec.atelier_color_level != 2)
            # For a subject the colour comes first, so the subject text cannot drown it out.
            prompt = painting_prompt(spec.model_id, color_text if spec.atelier_mode == "noise" else f"{color_text}, {text}")
            cfg = max(spec.cfg, spec.atelier_color_cfg or (COLOR_GUIDANCE_VIVID if spec.atelier_color_level == 2 else COLOR_GUIDANCE))
        notify(.02, "Ateliér: načítání modelu")
        source_url = None
        # The optional photographic study uses SDXL Base, then releases its pipeline before painting.
        if spec.atelier_mode == "photo":
            pipe = core.ensure_pipeline("sdxl_base", resident=2)
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
            pipe = core.ensure_pipeline(spec.model_id, resident=2)
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
            until = spec.atelier_color_until if color_text else 1.0
            if until < 1.0:
                # Two phases of one denoising run. The colour hint decides palette and layout in the first steps;
                # the rest runs without it (the artist's own prompt and CFG), because a text prompt present all the
                # way through measurably softens the brushwork (edge strength -27 %).
                latents = text_pipe(prompt=prompt, negative_prompt=None, width=spec.width, height=spec.height,
                    guidance_scale=cfg, num_inference_steps=spec.steps, generator=generator(), denoising_end=until, output_type="latent",
                    callback_on_step_end=core.build_step_callback(notify, .18, 1, 0, spec.steps, span=.72 * until, stage="Ateliér · barva"),
                    callback_on_step_end_tensor_inputs=[]).images
                result = pipe(prompt="" if spec.atelier_mode == "noise" else base_prompt, negative_prompt=None, image=latents, denoising_start=until,
                    guidance_scale=spec.cfg, num_inference_steps=spec.steps, generator=generator(),
                    callback_on_step_end=core.build_step_callback(notify, .18 + .72 * until, 1, 0, spec.steps, span=.72 * (1 - until), stage="Ateliér · tah"),
                    callback_on_step_end_tensor_inputs=[]).images[0]
                actual_steps = int(pipe.num_timesteps) + int(text_pipe.num_timesteps)
            else:
                result = text_pipe(prompt=prompt, negative_prompt=None, width=spec.width, height=spec.height,
                    guidance_scale=cfg, num_inference_steps=spec.steps, generator=generator(),
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
            "guidance_scale": cfg, "cfg": cfg, "requested_cfg": spec.cfg, "sampler": spec.sampler, "schedule": spec.schedule,
            "generation_width": spec.width, "generation_height": spec.height,
            "output_width": result.width, "output_height": result.height,
            "scale": spec.scale, "upscaler": "lanczos", "render_mode": "quick",
            "prompt": prompt, "negative_prompt": "", "denoise": spec.denoise if spec.atelier_mode == "photo" else None,
            "source_url": source_url, "source_name": title, "demo_mode": False,
            "photo_prompt": photo_prompt if spec.atelier_mode == "photo" else None,
            "photo_model_id": "sdxl_base" if spec.atelier_mode == "photo" else None,
            "generation_and_save_seconds": round(time.monotonic() - started, 2),
            "color_hint": color_text, "color_source": color_source, "color_level": spec.atelier_color_level if color_text else 0}
        image = {**core.encode_image(result, meta), "generation_meta": meta}
        output_images.append(image)
        if image_callback: image_callback(image, meta)
        last_meta = meta
        notify(1, "Ateliér: obraz uložen")
    return {"images": output_images, "meta": last_meta}
