"""Atelier Lab, round 2 (docs/atelier-lab-ramec.md, section 8): damage the INPUT photo, the MODEL, or both, then repaint.

Axis A, where the input is damaged before the model sees it (PIL, no weights touched):
  none     the photo as it is
  blur64   downscaled to 64 px wide and back (the "skeleton" that worked for Posun in the Nano Pro tests)
  tiles    8x8 grid, 25 % of the tiles shuffled among themselves (composition and palette stay, local meaning breaks)
Axis B, where the model is damaged in the first 30 % of the steps (same hooks as glitch_lab.py, a healthy checkpoint finishes):
  control, top_suppress, sa_identity, chan_drop   (the three that visibly changed the image in round 1, plus the control)

Repaint exactly as the app does it (app_runtime.repaint.repaint, artist prompt tokens, denoise 0.8), 2 checkpoints (Tuymans first) x 4 sources x 3 x 4 cells.
Run:  MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal run scripts/experiments/glitch_lab_img2img.py
Writes outputs/verification/glitch-lab-img2img/ (PNG per cell, results.json).
"""
import json
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-glitch-lab-img2img')
MODELS = ['tuymans_modal_2400', 'mulen_mara']
INPUTS = ['none', 'blur64', 'tiles']
OPS = ['control', 'top_suppress', 'sa_identity', 'chan_drop']
SOURCES = {  # name -> path relative to the repository root
    'thanatos': 'docs/vari-testy/fal-kolo5-thanatos/T_thanatos.jpg',
    'zaklad': 'docs/vari-testy/zdroje/A_source.jpg',
    'sopka': 'docs/vari-testy/fal-kolo4-zdroje/Z03.jpg',
    'soska': 'docs/vari-testy/fal-kolo4-zdroje/Z19.jpg',
}
STEPS, DENOISE, HEAL_FRACTION, SEED = 28, .8, .3, 11
BASE = {'generation_type': 'atelier', 'atelier_mode': 'archive', 'width': 1024, 'height': 1024, 'cfg': .5, 'steps': STEPS,
        'sampler': 'dpmpp_2m', 'schedule': 'karras', 'scale': 1, 'output_upscaler': 'lanczos', 'atelier_color_level': 0,
        'num_images': 1, 'denoise': DENOISE}


def damage_input(img, how, seed):
    import random
    from PIL import Image
    if how == 'none':
        return img
    if how == 'blur64':
        small = img.resize((64, max(1, round(64 * img.height / img.width))), Image.Resampling.LANCZOS)
        return small.resize(img.size, Image.Resampling.BICUBIC)
    rng = random.Random(seed)  # tiles
    n = 8
    tw, th = img.width // n, img.height // n
    cells = [(x, y) for x in range(n) for y in range(n)]
    chosen = rng.sample(cells, len(cells) // 4)
    shuffled = chosen[:]
    rng.shuffle(shuffled)
    out = img.copy()
    for (x, y), (sx, sy) in zip(chosen, shuffled):
        out.paste(img.crop((sx * tw, sy * th, (sx + 1) * tw, (sy + 1) * th)), (x * tw, y * th))
    return out


def install(op, pipe, state, rng, log):
    """Same operations as glitch_lab.py (copied: experiments are stand-alone). Returns a cleanup function."""
    import torch
    unet = pipe.unet
    handles, undo = [], []

    def active():
        return state['calls'] <= state['limit']

    handles.append(unet.register_forward_pre_hook(lambda module, args: state.__setitem__('calls', state['calls'] + 1)))

    def top_suppress(tensor):
        flat = tensor.abs().float().flatten()
        threshold = flat.kthvalue(max(1, int(flat.numel() * .95))).values
        return tensor.masked_fill(tensor.abs().float() >= threshold, 0)

    if op == 'top_suppress':
        def hook(module, args, out):
            return top_suppress(out) if active() else None
        handles.append(unet.mid_block.register_forward_hook(hook))
        handles.append(unet.up_blocks[0].register_forward_hook(hook))
    elif op == 'chan_drop':
        channels = unet.down_blocks[1].resnets[-1].out_channels
        chosen = torch.randperm(channels, generator=rng, device=unet.device)[:channels // 4]

        def drop(tensor):
            tensor = tensor.clone(); tensor[:, chosen] = 0; return tensor

        def hook(module, args, out):
            if not active():
                return None
            hidden, residuals = out
            return drop(hidden), tuple(drop(r) for r in residuals)
        handles.append(unet.down_blocks[1].register_forward_hook(hook))
    elif op == 'sa_identity':
        original = dict(unet.attn_processors)

        class Replacement:
            def __init__(self, inner):
                self.inner = inner

            def __call__(self, attn, hidden_states, *args, **kwargs):
                if not active():
                    return self.inner(attn, hidden_states, *args, **kwargs)
                return attn.to_out[1](attn.to_out[0](attn.to_v(hidden_states)))

        picked = [n for n in original if n.startswith('mid_block') and '.attn1.' in n]
        unet.set_attn_processor({n: (Replacement(p) if n in picked else p) for n, p in original.items()})
        undo.append(lambda: unet.set_attn_processor(original))

    def cleanup():
        for h in handles:
            h.remove()
        for fn in undo:
            fn()
    return cleanup


@app.function(image=gpu_image.add_local_python_source("modal_app"), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=3600, retries=0,
              env={'OUTPUTS_DIR': '/tmp/glitch-outputs', 'ARCHIVE_ROOT': '/published/atelier-archives'})
def run(sources, model_id):
    import io, time, zlib
    import numpy as np
    import torch
    from PIL import Image, ImageOps
    from app_runtime import core
    from app_runtime.repaint import repaint

    pipe = core.ensure_pipeline(model_id)
    schedule_steps, strength = core.inference_schedule(STEPS, DENOISE, True)
    run_steps = int(schedule_steps * strength)
    limit = int(HEAL_FRACTION * run_steps)
    print(f'schedule_steps={schedule_steps} strength={strength} -> about {run_steps} UNet calls, damage in the first {limit}', flush=True)

    def prepare(raw):
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
        scale = 1024 / max(img.size)
        return img.resize((max(8, round(img.width * scale / 8) * 8), max(8, round(img.height * scale / 8) * 8)), Image.Resampling.LANCZOS)

    def png(img):
        buffer = io.BytesIO(); img.save(buffer, format='PNG'); return buffer.getvalue()

    rows, started, firsts = [], time.monotonic(), {}
    for name, raw in sources.items():
        source = prepare(raw)
        for how in INPUTS:
            damaged = damage_input(source, how, SEED)
            if how != 'none':
                rows.append({'model': model_id, 'source': name, 'input': how, 'op': 'input_only_view', 'log': {}, 'png': png(damaged)})
            for op in OPS:
                state = {'calls': 0, 'limit': limit}
                rng = torch.Generator(device='cuda').manual_seed(SEED * 1000003 + zlib.crc32(op.encode()) % 100000)
                log = {}
                cleanup = install(op, pipe, state, rng, log) if op != 'control' else (lambda: None)
                try:
                    spec = core.parse_input({**BASE, 'model_id': model_id, 'seed': SEED})
                    result, meta = repaint(damaged, spec, SEED, None)
                finally:
                    cleanup()
                log['unet_calls'] = state['calls']
                if how == 'none' and op == 'control':
                    firsts[name] = np.asarray(result, dtype=np.int16)
                rows.append({'model': model_id, 'source': name, 'input': how, 'op': op, 'log': log, 'png': png(result)})
                print(f'{name} input={how} op={op} calls={state["calls"]} at {time.monotonic() - started:.0f}s', flush=True)
    # leak check: the very first control again
    name = next(iter(sources))
    spec = core.parse_input({**BASE, 'model_id': model_id, 'seed': SEED})
    again, _ = repaint(prepare(sources[name]), spec, SEED, None)
    leak = float(np.abs(np.asarray(again, dtype=np.int16) - firsts[name]).mean())
    print(f'LEAK CHECK: {leak:.3f}', flush=True)
    return {'rows': rows, 'leak_mean_abs_diff': leak}


@app.local_entrypoint()
def main():
    root = Path(__file__).resolve().parents[2]
    target = root / 'outputs/verification/glitch-lab-img2img'
    target.mkdir(parents=True, exist_ok=True)
    sources = {name: (root / path).read_bytes() for name, path in SOURCES.items()}
    summary = []
    for model, result in zip(MODELS, run.starmap([(sources, m) for m in MODELS], return_exceptions=True)):
        if isinstance(result, Exception):
            print(f'FAILED {model}: {result!r}')
            summary.append({'model': model, 'error': repr(result)[:2000]})
            continue
        for row in result['rows']:
            (target / f"{model}-{row['source']}-{row['input']}-{row['op']}.png").write_bytes(row.pop('png'))
            summary.append(row)
        summary.append({'model': model, 'leak_mean_abs_diff': result['leak_mean_abs_diff']})
        (target / 'results.json').write_text(json.dumps(summary, indent=2))
    print(f'Saved {len(summary)} entries to {target}')
