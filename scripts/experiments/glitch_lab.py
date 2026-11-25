"""Atelier Lab, round 1 (docs/atelier-lab-ramec.md): damage the SDXL UNet only in the first ~30 % of the steps, let the same
healthy checkpoint finish the run. Nothing in app_runtime is changed; every hook lives in this file and is removed after each cell.

Cells: checkpoint x seed x operation, 1024 px, 28 steps, dpmpp_2m karras, cfg 0.5, empty prompt (Volná studie), no colour hint.
At cfg 0.5 the pipeline runs one UNet call per step (no classifier-free guidance), so a call counter equals the step number.

Operations (all active in the first 8 of 28 steps unless noted):
  control        nothing
  mid_noise      Gaussian noise (1.5 x std of the tensor; 0.3 in the smoke test changed nothing) added to the output of the mid block
  top_suppress   the strongest 5 % of activations (by magnitude) of the mid block and of the first up block are ZEROED
  chan_drop      25 % of the channels of down block 1 are zeroed, in its hidden output and in its skip connections
  sa_identity    self-attention of the mid block: attention map replaced by identity (output = to_out(to_v(x)))
  xa_zero        output of all cross-attention layers of the up blocks zeroed (with an empty prompt the keys/values are the
                 empty-prompt embedding, not zeros, so this is still a real intervention)
  weight_noise   25 % of the per-tensor std (5 % in the smoke test changed nothing) added to every weight of the mid block (backup, restored after step 8)
  full_suppress  top_suppress during ALL 28 steps (no healing), the contrast case

Run:   MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal run scripts/experiments/glitch_lab.py [--smoke]
Writes outputs/verification/glitch-lab/ (PNG per cell, results.json). A leak check re-renders the control at the end.
"""
import json
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-glitch-lab')
MODELS = ['mulen_mara', 'hofmann_sdxl', 'tuymans_modal_2400']
SEEDS = [11, 2024, 70707, 913]
OPS = ['control', 'mid_noise', 'top_suppress', 'chan_drop', 'sa_identity', 'xa_zero', 'weight_noise', 'full_suppress']
STEPS = 28
HEAL_FRACTION = .3
BASE = {'generation_type': 'atelier', 'atelier_mode': 'noise', 'atelier_framing': 'crop', 'width': 1024, 'height': 1024,
        'cfg': .5, 'steps': STEPS, 'sampler': 'dpmpp_2m', 'schedule': 'karras', 'scale': 1, 'output_upscaler': 'lanczos',
        'atelier_color_level': 0, 'num_images': 1}


def install(op, pipe, state, rng, log):
    """Attach the hooks of one operation to pipe.unet. Returns a cleanup function that undoes everything."""
    import torch
    unet = pipe.unet
    handles, undo = [], []

    def active():
        return state['calls'] <= state['limit']

    def count(module, args):
        state['calls'] += 1
        if state['calls'] == state['limit'] + 1 and state.get('heal'):
            state['heal']()  # the damage stops here; weights are restored for the remaining steps

    handles.append(unet.register_forward_pre_hook(count))

    def top_suppress(tensor):
        flat = tensor.abs().float().flatten()
        threshold = flat.kthvalue(max(1, int(flat.numel() * .95))).values
        zeroed = tensor.abs().float() >= threshold
        log.setdefault('zeroed_fraction', []).append(round(float(zeroed.float().mean()), 4))
        return tensor.masked_fill(zeroed, 0)

    if op == 'mid_noise':
        def hook(module, args, out):
            if not active():
                return None
            return out + torch.randn(out.shape, generator=rng, device=out.device, dtype=out.dtype) * (1.5 * out.float().std()).to(out.dtype)
        handles.append(unet.mid_block.register_forward_hook(hook))

    elif op in ('top_suppress', 'full_suppress'):
        if op == 'full_suppress':
            state['limit'] = 10 ** 6

        def hook(module, args, out):
            return top_suppress(out) if active() else None
        handles.append(unet.mid_block.register_forward_hook(hook))
        handles.append(unet.up_blocks[0].register_forward_hook(hook))

    elif op == 'chan_drop':
        channels = unet.down_blocks[1].resnets[-1].out_channels
        chosen = torch.randperm(channels, generator=rng, device=unet.device)[:channels // 4]
        log['dropped_channels'] = int(chosen.numel()); log['of'] = int(channels)

        def drop(tensor):
            tensor = tensor.clone(); tensor[:, chosen] = 0; return tensor

        def hook(module, args, out):
            if not active():
                return None
            hidden, residuals = out
            return drop(hidden), tuple(drop(r) for r in residuals)
        handles.append(unet.down_blocks[1].register_forward_hook(hook))

    elif op in ('sa_identity', 'xa_zero'):
        original = dict(unet.attn_processors)

        class Replacement:
            def __init__(self, inner):
                self.inner = inner

            def __call__(self, attn, hidden_states, *args, **kwargs):
                if not active():
                    return self.inner(attn, hidden_states, *args, **kwargs)
                if op == 'sa_identity':
                    return attn.to_out[1](attn.to_out[0](attn.to_v(hidden_states)))
                return torch.zeros_like(hidden_states)

        if op == 'sa_identity':
            picked = [n for n in original if n.startswith('mid_block') and '.attn1.' in n]
        else:
            picked = [n for n in original if n.startswith('up_blocks') and '.attn2.' in n]
        log['replaced_processors'] = len(picked)
        unet.set_attn_processor({n: (Replacement(p) if n in picked else p) for n, p in original.items()})
        undo.append(lambda: unet.set_attn_processor(original))

    elif op == 'weight_noise':
        params = list(unet.mid_block.parameters())
        backup = [p.detach().clone() for p in params]
        restored = {'done': False}

        def restore():
            if not restored['done']:
                with torch.no_grad():
                    for p, b in zip(params, backup):
                        p.copy_(b)
                restored['done'] = True
        with torch.no_grad():
            for p in params:
                p.add_(torch.randn(p.shape, generator=rng, device=p.device, dtype=p.dtype) * (.25 * p.float().std()).to(p.dtype))
        state['heal'] = restore
        undo.append(restore)
        log['params'] = len(params)

    def cleanup():
        for h in handles:
            h.remove()
        for fn in undo:
            fn()
    return cleanup


@app.function(image=gpu_image.add_local_python_source("modal_app"), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=3600, retries=0,
              env={'OUTPUTS_DIR': '/tmp/glitch-outputs', 'ARCHIVE_ROOT': '/published/atelier-archives'})
def run(model_id, smoke):
    import base64, io, time, zlib
    import numpy as np
    import torch
    from PIL import Image
    from app_runtime import core
    from app_runtime.atelier import generate_study

    pipe = core.ensure_pipeline(model_id)  # the same cached object generate_study will get back
    unet = pipe.unet
    print('BLOCKS', model_id, flush=True)
    for name, blocks in (('down', unet.down_blocks), ('up', unet.up_blocks)):
        for i, block in enumerate(blocks):
            print(f'  {name}[{i}] {type(block).__name__} attentions={len(getattr(block, "attentions", []) or [])}', flush=True)
    print(f'  mid {type(unet.mid_block).__name__} xformers={getattr(pipe, "_studio_xformers", None)}', flush=True)

    def png(img):
        buffer = io.BytesIO(); img.save(buffer, format='PNG'); return buffer.getvalue()

    def render(seed, op):
        state = {'calls': 0, 'limit': int(HEAL_FRACTION * STEPS)}
        rng = torch.Generator(device='cuda').manual_seed(seed * 1000003 + zlib.crc32(op.encode()) % 100000)
        log = {}
        cleanup = install(op, pipe, state, rng, log) if op != 'control' else (lambda: None)
        try:
            spec = core.parse_input({**BASE, 'model_id': model_id, 'seed': seed})
            out = generate_study(spec, None, None)
        finally:
            cleanup()
        raw = base64.b64decode(out['images'][0]['image_base64'])
        log['unet_calls'] = state['calls']
        return Image.open(io.BytesIO(raw)).convert('RGB'), log

    started, rows, first_control = time.monotonic(), [], {}
    seeds = SEEDS[:1] if smoke else SEEDS
    for seed in seeds:
        for op in OPS:
            img, log = render(seed, op)
            if op == 'control':
                first_control[seed] = np.asarray(img, dtype=np.int16)
            rows.append({'model': model_id, 'seed': seed, 'op': op, 'log': log, 'png': png(img)})
            print(f'{model_id} seed {seed} {op} {log} at {time.monotonic() - started:.0f}s', flush=True)
    img, _ = render(seeds[0], 'control')
    leak = float(np.abs(np.asarray(img, dtype=np.int16) - first_control[seeds[0]]).mean())
    print(f'LEAK CHECK {model_id}: mean abs pixel difference of two controls = {leak:.3f}', flush=True)
    return {'model': model_id, 'rows': rows, 'leak_mean_abs_diff': leak}


@app.local_entrypoint()
def main(smoke: bool = False, only: str = ''):
    root = Path(__file__).resolve().parents[2]
    target = root / 'outputs/verification/glitch-lab'
    target.mkdir(parents=True, exist_ok=True)
    chosen = [m for m in MODELS if not only or m in only.split(',')]
    summary = []
    for model, result in zip(chosen[:1] if smoke else chosen, run.starmap([(m, smoke) for m in (chosen[:1] if smoke else chosen)], return_exceptions=True)):
        if isinstance(result, Exception):
            print(f'FAILED {model}: {result!r}')
            summary.append({'model': model, 'error': repr(result)[:2000]})
            continue
        for row in result['rows']:
            (target / f"{row['model']}-{row['seed']}-{row['op']}.png").write_bytes(row.pop('png'))
            summary.append(row)
        summary.append({'model': result['model'], 'leak_mean_abs_diff': result['leak_mean_abs_diff']})
        (target / 'results.json').write_text(json.dumps(summary, indent=2))  # saved after every model
    (target / 'results.json').write_text(json.dumps(summary, indent=2))
    print(f'Saved {len(summary)} entries to {target}')
