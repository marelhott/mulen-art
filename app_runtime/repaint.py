"""Shared artist-checkpoint pass for photographic and archive studies."""

DEFAULT_REPAINT_DENOISE = 0.82


def repaint(source, spec, seed, progress):
    from . import core
    from .atelier import painting_prompt

    pipe = core.ensure_pipeline(spec.model_id, resident=2 if spec.atelier_mode == "photo" else 1)
    core.ensure_lora(pipe, "none", 0)
    pipe.scheduler = core.make_scheduler(pipe.scheduler.config, spec.sampler, spec.schedule)
    # Only verified learned caption tokens, never an invented artist/style description.
    prompt = painting_prompt(spec.model_id, "").rstrip(", ")
    cfg = max(spec.cfg, 3.0) if prompt else spec.cfg
    schedule_steps, strength = core.inference_schedule(spec.steps, spec.denoise, True)
    result = pipe(
        prompt=prompt, negative_prompt=None, image=source, strength=strength,
        guidance_scale=cfg, num_inference_steps=schedule_steps,
        generator=core.get_torch().Generator(device="cuda").manual_seed(seed),
        callback_on_step_end=core.build_step_callback(progress, 0, 1, 0, spec.steps, span=1, stage="Přemalování"),
        callback_on_step_end_tensor_inputs=[],
    ).images[0]
    return result, {
        "repaint_version": "artist-v2", "prompt": prompt, "negative_prompt": "",
        "cfg": cfg, "guidance_scale": cfg, "requested_cfg": spec.cfg,
        "denoise": spec.denoise, "effective_strength": strength,
        "steps": spec.steps, "schedule_steps": schedule_steps,
        "actual_steps": int(pipe.num_timesteps), "steps_mode": "actual",
    }
