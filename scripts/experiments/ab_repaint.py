"""Bounded A/B of repaint switches on the same sources and seeds. Defaults of the app are untouched.

Variants (all share source, seed, model, sampler, steps and denoise):
  baseline  current behaviour (guidance floor 3, tiled VAE)
  noguide   no text guidance at all: cfg 0.5, floor 0 (the recipe behind most images kept in the library)
  notiling  baseline with the tiled VAE decode switched off

Run:  uv run --python 3.12 --with modal --with httpx python -m modal run scripts/ab_repaint.py --model tuymans_modal_2400 --count 6
Needs the Modal profile that owns the workspace (MODAL_PROFILE=img2img) and .modal-app-credentials.json.
Writes outputs/verification/ab-repaint/ (one PNG per variant plus results.json). 6 sources x 3 variants stays below ~$2.
"""
import json
from pathlib import Path
import modal
from modal_app import gpu_image, models, archives, outputs

app = modal.App('img2img-ab-repaint')
VARIANTS = {
    'baseline': {},
    'noguide': {'cfg': 0.5, 'repaint_cfg_floor': 0},
    'notiling': {'vae_tiling': False},
}


@app.function(image=gpu_image.add_local_python_source("modal_app"),
              volumes={'/models': models, '/archives': archives, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=1500, retries=0)
def run(records, model_id):
    import io, time
    from PIL import Image
    from app_runtime import core
    from app_runtime.repaint import repaint
    started, results = time.monotonic(), []
    for record in records:
        settings = record['settings']
        with Image.open(Path('/published') / Path(settings['source_url']).name) as raw:
            source = raw.convert('RGB')
        row = {'id': record['id'], 'seed': settings['seed'], 'variants': {}}
        for name, extra in VARIANTS.items():
            spec = core.parse_input({'generation_type': 'atelier', 'atelier_mode': settings['atelier_mode'],
                'model_id': model_id, 'cfg': .5, 'denoise': .82, 'steps': 28, 'scale': 1,
                'sampler': settings['sampler'], 'schedule': settings['schedule'], **extra})
            image, meta = repaint(source, spec, settings['seed'], None)
            buffer = io.BytesIO(); image.save(buffer, format='PNG')
            row['variants'][name] = {'png': buffer.getvalue(), 'cfg': meta['cfg'], 'vae_tiling': meta['vae_tiling']}
        buffer = io.BytesIO(); source.save(buffer, format='PNG'); row['source'] = buffer.getvalue()
        results.append(row)
        print(f"{record['id']} done in {time.monotonic()-started:.0f}s", flush=True)
    return results


@app.local_entrypoint()
def main(model: str = 'tuymans_modal_2400', count: int = 6):
    import httpx
    root = Path(__file__).resolve().parents[2]
    credentials = json.loads((root / '.modal-app-credentials.json').read_text())
    with httpx.Client(base_url='https://mailhospodarsky--i.modal.run',
                      auth=(credentials['STUDIO_USERNAME'], credentials['STUDIO_PASSWORD']), timeout=90) as client:
        history = client.get('/api/history').json()['items']
    chosen = [i for i in history if i.get('settings', {}).get('atelier_mode') == 'photo'
              and str(i['settings'].get('source_url', '')).startswith('/library/') and i['settings'].get('seed') is not None][:count]
    if not chosen:
        raise RuntimeError('No retained photo-mode sources available')
    target = root / 'outputs/verification/ab-repaint'
    target.mkdir(parents=True, exist_ok=True)
    summary = []
    for index, row in enumerate(run.remote(chosen, model), 1):
        (target / f'{index:02d}-source.png').write_bytes(row.pop('source'))
        for name, variant in row['variants'].items():
            (target / f'{index:02d}-{name}.png').write_bytes(variant.pop('png'))
        summary.append(row)
    (target / 'results.json').write_text(json.dumps(summary, indent=2))
    print(f'Saved {len(summary)} comparisons to {target}')
