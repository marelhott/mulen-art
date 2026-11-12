"""Bounded GPU comparison of six existing sources; does not enqueue production jobs."""
import json
from pathlib import Path
import modal
from modal_app import gpu_image, models, archives, outputs

app = modal.App('img2img-repaint-verification')


@app.function(image=gpu_image.add_local_python_source("modal_app"),
              volumes={'/models': models, '/archives': archives, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=900, retries=0)
def verify(records):
    import io, time
    from PIL import Image
    from app_runtime import core
    from app_runtime.repaint import repaint
    started = time.monotonic()
    results = []
    # One GPU, serial execution, <= 900 s. At the configured L4/A10G rates this stays below $2.
    for record in records:
        settings = record['settings']
        source_path = Path('/published') / Path(settings['source_url']).name
        with Image.open(source_path) as raw:
            source = raw.convert('RGB')
        spec = core.parse_input({'generation_type': 'atelier', 'atelier_mode': settings['atelier_mode'],
            'model_id': settings['model_id'], 'cfg': .5, 'denoise': .82, 'steps': 28, 'scale': 1,
            'sampler': settings['sampler'], 'schedule': settings['schedule']})
        image, meta = repaint(source, spec, settings['seed'], None)
        def png(picture):
            buffer = io.BytesIO(); picture.save(buffer, format='PNG'); return buffer.getvalue()
        with Image.open(Path('/published') / record['filename']) as old:
            before = old.convert('RGB'); before.thumbnail(source.size)
        results.append({'id': record['id'], 'mode': settings['atelier_mode'],
                        'model_id': settings['model_id'], 'baseline_model': record['baseline_model'], 'source': png(source),
                        'before': png(before), 'after': png(image), 'meta': meta})
        print(f"Verified {settings['atelier_mode']} / {settings['model_id']} in {time.monotonic()-started:.1f}s", flush=True)
    return results


@app.local_entrypoint()
def main():
    import httpx
    root = Path(__file__).resolve().parents[1]
    credentials = json.loads((root / '.modal-app-credentials.json').read_text())
    with httpx.Client(base_url='https://mailhospodarsky--i.modal.run',
                      auth=(credentials['STUDIO_USERNAME'], credentials['STUDIO_PASSWORD']), timeout=90) as client:
        response = client.get('/api/history'); response.raise_for_status()
        history = response.json()['items']
    records = []
    for model in ['tuymans_modal_2400', 'hofmann_sdxl', 'mulen_mara']:
        for mode in ['photo', 'archive']:
            candidates = [i for i in history if i.get('settings', {}).get('atelier_mode') == mode]
            if not candidates:
                raise RuntimeError(f'No retained {mode} source available')
            chosen = next((i for i in candidates if i['settings'].get('model_id') == model), candidates[0])
            records.append({**chosen, 'baseline_model': chosen['settings']['model_id'],
                            'settings': {**chosen['settings'], 'model_id': model}})
    target = root / 'outputs/verification/repaint-v2'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'inputs.json').write_text(json.dumps(records, indent=2))
    results = verify.remote(records)
    summary = []
    for index, result in enumerate(results):
        prefix = f"{index+1:02d}-{result['mode']}-{result['model_id']}"
        for kind in ['source', 'before', 'after']:
            (target / f'{prefix}-{kind}.png').write_bytes(result.pop(kind))
        summary.append(result)
    (target / 'results.json').write_text(json.dumps(summary, indent=2))
    print(f'Saved {len(results)} comparisons to {target}')
