"""Check of app_runtime/glitch.py on the GPU (the option added to Ateliér and to the Vari unCLIP pre-stage).

1. Ateliér: generate_study with glitch=<op> must reproduce the experiment images of scripts/experiments/glitch_lab.py
   (outputs/verification/glitch-lab/mulen_mara-11-<op>.png; same checkpoint, seed, settings) pixel for pixel or very nearly.
2. unCLIP (SD 2.1): every operation must run on that UNet, change the picture, and a control rendered afterwards must equal the first
   control (the cached pipeline is not left damaged).

Run:  MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal run scripts/experiments/glitch_check.py
Writes outputs/verification/glitch-check/. A few cents on one L4.
"""
import base64
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-glitch-check')
OPS = ['top_suppress', 'chan_drop', 'sa_identity']
BASE = {'generation_type': 'atelier', 'atelier_mode': 'noise', 'atelier_framing': 'crop', 'width': 1024, 'height': 1024, 'cfg': .5,
        'steps': 28, 'sampler': 'dpmpp_2m', 'schedule': 'karras', 'scale': 1, 'output_upscaler': 'lanczos', 'atelier_color_level': 0,
        'num_images': 1, 'model_id': 'mulen_mara', 'seed': 11}


@app.function(image=gpu_image.add_local_python_source("modal_app"), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=3000, retries=0,
              env={'OUTPUTS_DIR': '/tmp/glitch-check', 'ARCHIVE_ROOT': '/published/atelier-archives'})
def run(source_b64):
    from app_runtime import core, unclip
    from app_runtime.atelier import generate_study
    results = {'atelier': {}, 'unclip': {}}
    for op in OPS:
        out = generate_study(core.parse_input({**BASE, 'glitch': op}), None, None)
        results['atelier'][op] = (base64.b64decode(out['images'][0]['image_base64']), out['meta'].get('glitch'), out['meta'].get('glitch_until'))
    payload = {'generation_type': 'reimagine', 'reimagine_mode': 'unclip', 'image_base64': source_b64, 'long_side': 1024, 'steps': 35,
               'cfg': 5.0, 'num_images': 1, 'seed': 5, 'denoise': .8, 'noise_level': 0}
    for name, op in [('control', ''), *[(op, op) for op in OPS], ('control_again', '')]:
        out = unclip.generate_variations(core.parse_input({**payload, 'glitch': op}), None, None)
        results['unclip'][name] = (base64.b64decode(out['images'][0]['image_base64']), out['meta'].get('glitch'))
        print(f'unclip {name} done', flush=True)
    return results


@app.local_entrypoint()
def main():
    root = Path(__file__).resolve().parents[2]
    target = root / 'outputs/verification/glitch-check'
    target.mkdir(parents=True, exist_ok=True)
    source = base64.b64encode((root / 'docs/vari-testy/zdroje/A_source.jpg').read_bytes()).decode()
    results = run.remote(source)
    for op, (data, name, until) in results['atelier'].items():
        (target / f'atelier-{op}.png').write_bytes(data)
        print(f'atelier {op}: meta glitch={name} until={until}')
    for name, (data, meta) in results['unclip'].items():
        (target / f'unclip-{name}.png').write_bytes(data)
        print(f'unclip {name}: meta glitch={meta}')
    print('Saved to', target)
