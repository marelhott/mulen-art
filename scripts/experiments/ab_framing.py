"""A/B: cropped vs whole framing of the curated Atelier subjects, same checkpoint and seed.

Run:  MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal python -m modal run scripts/experiments/ab_framing.py
Writes outputs/verification/ab-framing/. 3 checkpoints x 4 themes x 2 framings = 24 images, well below $1.
"""
import base64
import io
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-ab-framing')
MODELS = ['mulen_mara', 'hofmann_sdxl', 'tuymans_modal_2400']
THEMES = ['face', 'interior', 'object', 'landscape']
BASE = {'generation_type': 'atelier', 'atelier_mode': 'subject', 'width': 1024, 'height': 1024, 'cfg': .5, 'steps': 28,
        'sampler': 'dpmpp_2m', 'schedule': 'karras', 'scale': 1, 'output_upscaler': 'lanczos', 'atelier_color_level': 2, 'num_images': 1}


@app.function(image=gpu_image.add_local_python_source("modal_app"), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=3000, retries=0,
              env={'OUTPUTS_DIR': '/tmp/ab-outputs', 'ARCHIVE_ROOT': '/published/atelier-archives'})
def run(model_id):
    from app_runtime import core
    from app_runtime.atelier import generate_study
    rows = []
    for theme in THEMES:
        row = {'model': model_id, 'theme': theme, 'png': {}}
        for framing in ('crop', 'whole'):
            spec = core.parse_input({**BASE, 'model_id': model_id, 'seed': 4242, 'atelier_theme': theme, 'atelier_framing': framing})
            out = generate_study(spec, None, None)
            row['png'][framing] = base64.b64decode(out['images'][0]['image_base64'])
            row['text_' + framing] = out['meta']['subject_text']
        rows.append(row)
    return rows


@app.local_entrypoint()
def main():
    from PIL import Image, ImageDraw
    target = Path(__file__).resolve().parents[2] / 'outputs/verification/ab-framing'
    target.mkdir(parents=True, exist_ok=True)
    T = 300
    for rows in run.map(MODELS):
        model = rows[0]['model']
        sheet = Image.new('RGB', (T * len(rows) , (T + 14) * 2), 'white'); draw = ImageDraw.Draw(sheet)
        for j, row in enumerate(rows):
            for i, framing in enumerate(('crop', 'whole')):
                img = Image.open(io.BytesIO(row['png'][framing])).convert('RGB').resize((T, T))
                sheet.paste(img, (j * T, i * (T + 14) + 14)); draw.text((j * T + 3, i * (T + 14) + 2), f"{framing} | {row['theme']}", fill='black')
        sheet.save(target / f'sheet-{model}.jpg', quality=88); print(model)
