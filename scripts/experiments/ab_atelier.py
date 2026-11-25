"""Bounded A/B for a fuller Ateliér (docs/atelier-smer.md). Defaults of the app are untouched.

Variants per (checkpoint, seed), all with the app's Ateliér defaults (1024 px, cfg 0.5, 28 steps, dpmpp_2m karras, vivid colour hint):
  control    current "Volná studie" (noise mode, colour hint for the first 20 % of the steps)
  spatial    the same, but the first 30 % also carries one spatial phrase taken from the artists' own training captions
  collision  underpainting from 2-3 crops of the archives collided diagonally, contrast pushed, repainted at denoise 0.9
  coll2      collision + a second short pass of the same checkpoint at 1536 px with light grain (denoise 0.28)

Run:  MODAL_PROFILE=img2img uv run --python 3.12 --with modal python -m modal run scripts/experiments/ab_atelier.py
Writes outputs/verification/ab-atelier/ (PNG per cell, underpaintings, results.json). ~48 images on one L4, well below $1.
"""
import json
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-ab-atelier')
MODELS = ['mulen_mara', 'hofmann_sdxl', 'tuymans_modal_2400']
SEEDS = [11, 2024, 70707, 913]
SPATIAL = ['against a dark ground', 'seen from above', 'reflected in a dark floor', 'cut off by the top edge',
           'against darkness', 'seen from below', 'against a pale ground', 'against black']
BASE = {'generation_type': 'atelier', 'atelier_mode': 'noise', 'width': 1024, 'height': 1024, 'cfg': .5, 'steps': 28,
        'sampler': 'dpmpp_2m', 'schedule': 'karras', 'scale': 1, 'output_upscaler': 'lanczos', 'atelier_color_level': 2, 'num_images': 1}


def underpainting(seed, size=1024):
    """Collide 2-3 random archive crops: rotate, diagonal feathered seam, one inset block, contrast pushed."""
    import random
    from PIL import Image, ImageOps, ImageFilter, ImageDraw, ImageChops
    from app_runtime.archives import load_manifest, archive_root
    rng = random.Random(seed * 7919)
    items = [(a['id'], it) for a in load_manifest()['archives'] for it in a.get('items', [])]
    picks = rng.sample(items, 3)

    def crop(item):
        with Image.open(archive_root() / item['path']) as raw:
            img = ImageOps.exif_transpose(raw).convert('RGB')
        frac = rng.uniform(.4, .75)
        w, h = int(img.width * frac), int(img.height * frac)
        x, y = rng.randint(0, img.width - w), rng.randint(0, img.height - h)
        img = img.crop((x, y, x + w, y + h)).rotate(rng.choice([0, 0, 90, 180, 270]) + rng.uniform(-12, 12), expand=False, fillcolor=(20, 20, 20))
        return ImageOps.fit(img, (size, size))

    a, b, c = (crop(it) for _, it in picks)
    mask = Image.new('L', (size, size), 0)
    x0, x1 = rng.randint(0, size), rng.randint(0, size)
    ImageDraw.Draw(mask).polygon([(x0, 0), (size, 0), (size, size), (x1, size)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(rng.uniform(4, 40)))
    out = Image.composite(b, a, mask)
    if rng.random() < .7:  # one inset block, a hard seam
        bw, bh = rng.randint(size // 5, size // 2), rng.randint(size // 5, size // 2)
        bx, by = rng.randint(0, size - bw), rng.randint(0, size - bh)
        out.paste(c.resize((bw, bh)), (bx, by))
    out = ImageOps.autocontrast(out, cutoff=2)
    lut = [min(255, int(255 * ((i / 255) ** 1.35))) for i in range(256)]  # deeper darks
    out = out.point(lut * 3)
    return out, [f'{aid}:{it.get("filename") or it.get("id")}' for aid, it in picks]


@app.function(image=gpu_image.add_local_python_source("modal_app"), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=3600, retries=0,
              env={'OUTPUTS_DIR': '/tmp/ab-outputs', 'ARCHIVE_ROOT': '/published/atelier-archives'})
def run(model_id):
    import io, random, time
    import numpy as np
    from PIL import Image
    from app_runtime import core
    from app_runtime.atelier import generate_study, color_hint
    from app_runtime.repaint import repaint

    def png(img):
        buffer = io.BytesIO(); img.save(buffer, format='PNG'); return buffer.getvalue()

    def study(seed, **extra):
        spec = core.parse_input({**BASE, 'model_id': model_id, 'seed': seed, **extra})
        out = generate_study(spec, None, None)
        import base64
        raw = base64.b64decode(out['images'][0]['image_base64'])
        return Image.open(io.BytesIO(raw)).convert('RGB'), out['meta']

    started, rows = time.monotonic(), []
    for seed in SEEDS:
        row = {'model': model_id, 'seed': seed, 'png': {}}
        img, meta = study(seed)
        row['png']['control'], row['color'] = png(img), meta.get('color_hint')
        phrase = random.Random(seed).choice(SPATIAL)
        color, _ = color_hint(model_id, seed, adjectives=False)
        img, meta = study(seed, atelier_color_text=f'{color}, {phrase}', atelier_color_until=.3)
        row['png']['spatial'], row['phrase'] = png(img), phrase
        under, picks = underpainting(seed)
        row['png']['under'], row['picks'] = png(under), picks
        spec = core.parse_input({**BASE, 'atelier_mode': 'archive', 'model_id': model_id, 'denoise': .9})
        img, meta = repaint(under, spec, seed, None)
        row['png']['collision'], row['collision_cfg'] = png(img), meta['cfg']
        big = img.resize((1536, 1536), Image.Resampling.LANCZOS)
        noise = np.random.default_rng(seed).normal(0, 6, (1536, 1536, 1))
        big = Image.fromarray(np.clip(np.asarray(big, dtype=np.float32) + noise, 0, 255).astype('uint8'))
        spec2 = core.parse_input({**BASE, 'atelier_mode': 'archive', 'model_id': model_id, 'denoise': .28, 'width': 1536, 'height': 1536})
        img2, _ = repaint(big, spec2, seed, None)
        row['png']['coll2'] = png(img2)
        rows.append(row)
        print(f'{model_id} seed {seed} done at {time.monotonic() - started:.0f}s', flush=True)
    return rows


@app.local_entrypoint()
def main():
    root = Path(__file__).resolve().parents[2]
    target = root / 'outputs/verification/ab-atelier'
    target.mkdir(parents=True, exist_ok=True)
    summary = []
    for rows in run.map(MODELS):
        for row in rows:
            for name, data in row.pop('png').items():
                (target / f"{row['model']}-{row['seed']}-{name}.png").write_bytes(data)
            summary.append(row)
    (target / 'results.json').write_text(json.dumps(summary, indent=2))
    print(f'Saved {len(summary)} rows to {target}')
