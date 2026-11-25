"""Read-only: do simple image measures separate Atelier studies you kept (library) from those you deleted?

Measures per thumbnail (all label-free, so they can later run on an early-step preview): tonal range (p5-p95 of luminance),
dark share, off-centre mass (distance of the luminance-weighted centroid from the centre), edge density (structure),
edge spread (how unevenly the structure is spread over a 4x4 grid: calm field + one busy place scores high), saturation,
hue count. Prints per group means and a simple AUC of every measure for lib vs del (0.5 = no signal).

Run:  MODAL_PROFILE=img2img uv run -q --python 3.12 --with modal --with numpy python -m modal run scripts/experiments/curator_measures.py
Writes outputs/verification/curator/measures.json (one row per record) for later analysis.
"""
import json
from pathlib import Path
import modal

app = modal.App('mulen-curator-measures')
outputs = modal.Volume.from_name('img2img-outputs')
image = modal.Image.debian_slim(python_version='3.11').pip_install('pillow', 'numpy')


@app.function(image=image, volumes={'/outputs': outputs}, cpu=2, memory=2048, timeout=1800)
def measure():
    import numpy as np
    from PIL import Image
    rows = []
    for path in Path('/outputs').glob('*.json'):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(data, dict) or 'filename' not in data:
            continue
        settings = data.get('settings') or {}
        if settings.get('generation_type') != 'atelier':
            continue
        state = 'lib' if data.get('saved_to_library') else ('del' if data.get('deleted') else 'keep')
        thumb = Path('/outputs/thumbs') / (Path(data['filename']).stem + '.webp')
        if not thumb.exists():
            continue
        try:
            with Image.open(thumb) as raw:
                img = raw.convert('RGB').resize((256, 256), Image.Resampling.BILINEAR)
        except Exception:
            continue
        rgb = np.asarray(img, dtype=np.float32) / 255
        lum = rgb @ np.array([.299, .587, .114], dtype=np.float32)
        p5, p95 = np.percentile(lum, [5, 95])
        ys, xs = np.mgrid[0:256, 0:256]
        weight = (1 - lum) + 1e-6  # dark mass carries the weight in these paintings
        cy, cx = (weight * ys).sum() / weight.sum(), (weight * xs).sum() / weight.sum()
        offcentre = float(np.hypot(cy - 127.5, cx - 127.5) / 180)
        gy, gx = np.gradient(lum)
        edge = np.hypot(gx, gy)
        cells = edge.reshape(4, 64, 4, 64).mean(axis=(1, 3)).ravel()
        mx, mn = rgb.max(axis=2), rgb.min(axis=2)
        sat = float(((mx - mn) / (mx + 1e-6)).mean())
        hsv_hue = np.arctan2(np.sqrt(3) * (rgb[..., 1] - rgb[..., 2]), 2 * rgb[..., 0] - rgb[..., 1] - rgb[..., 2])
        hue_hist = np.histogram(hsv_hue[(mx - mn) > .15], bins=12, range=(-np.pi, np.pi))[0]
        rows.append({'id': data['id'], 'state': state, 'mode': settings.get('atelier_mode'), 'model': data.get('model_id'),
                     'day': data['created_at'][:10], 'tonal_range': float(p95 - p5), 'dark_share': float((lum < .25).mean()),
                     'offcentre': offcentre, 'edge': float(edge.mean()), 'edge_spread': float(cells.std() / (cells.mean() + 1e-6)),
                     'saturation': sat, 'hue_count': int((hue_hist > hue_hist.sum() * .06).sum())})
    return rows


def auc(a, b):
    """P(random lib value > random del value); 0.5 = no signal."""
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    if not len(a) or not len(b):
        return float('nan')
    return float(((a[:, None] > b[None, :]).sum() + .5 * (a[:, None] == b[None, :]).sum()) / (len(a) * len(b)))


@app.local_entrypoint()
def main():
    import collections
    import numpy as np
    rows = measure.remote()
    target = Path(__file__).resolve().parents[2] / 'outputs/verification/curator'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'measures.json').write_text(json.dumps(rows))
    print(len(rows), 'atelier records', dict(collections.Counter(r['state'] for r in rows)))
    keys = ['tonal_range', 'dark_share', 'offcentre', 'edge', 'edge_spread', 'saturation', 'hue_count']
    for title, subset in [('all atelier', rows)] + [(f'mode={m}', [r for r in rows if r['mode'] == m]) for m in ('noise', 'subject', 'photo', 'archive')]:
        lib = [r for r in subset if r['state'] == 'lib']
        dele = [r for r in subset if r['state'] != 'lib']  # atelier has no deleted records: not saved = the negatives
        if len(lib) < 3 or len(dele) < 3:
            print(f'\n## {title}: saved={len(lib)} not_saved={len(dele)} (too few)')
            continue
        print(f'\n## {title}: saved={len(lib)} not_saved={len(dele)}')
        for k in keys:
            print(f"  {k:12} lib={np.mean([r[k] for r in lib]):.3f}  del={np.mean([r[k] for r in dele]):.3f}  AUC={auc([r[k] for r in lib], [r[k] for r in dele]):.2f}")
