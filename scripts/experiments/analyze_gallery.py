"""Read-only: which settings produce images you keep? Tabulates kept / library / deleted by setting.

Run:  MODAL_PROFILE=img2img uv run --python 3.12 --with modal python -m modal run scripts/analyze_gallery.py
Deleted images stay recoverable for 30 days, so very recent "kept" rows may simply be unreviewed.
Pass --skip-days 2026-10-22,2026-10-21 to leave out bulk test days.
"""
import collections, json
import modal

app = modal.App('mulen-analyze-gallery')
outputs = modal.Volume.from_name('img2img-outputs')
image = modal.Image.debian_slim(python_version='3.11')


@app.function(image=image, volumes={'/outputs': outputs}, cpu=1, memory=1024, timeout=900)
def dump():
    from pathlib import Path
    rows = []
    for path in Path('/outputs').glob('*.json'):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict) and 'filename' in data:
            rows.append({k: v for k, v in data.items() if not (isinstance(v, str) and len(v) > 600)})
    return rows


def state(row):
    return 'lib' if row.get('saved_to_library') else ('del' if row.get('deleted') else 'keep')


def table(rows, title, key, minimum=8):
    counts = collections.defaultdict(collections.Counter)
    for row in rows:
        try:
            counts[key(row, row.get('settings', {}))][state(row)] += 1
        except Exception:
            counts['?'][state(row)] += 1
    print(f'\n## {title}')
    for label, c in sorted(counts.items(), key=lambda item: -sum(item[1].values())):
        n = sum(c.values())
        if n >= minimum:
            print(f"{str(label)[:56]:56} n={n:4} lib={c['lib']:3} keep={c['keep']:3} del={c['del']:3} kept%={100 * (n - c['del']) / n:.0f}")


@app.local_entrypoint()
def main(skip_days: str = ''):
    skipped = set(filter(None, skip_days.split(',')))
    rows = [r for r in dump.remote() if r['created_at'][:10] not in skipped]
    print(len(rows), 'records', dict(collections.Counter(state(r) for r in rows)))
    mode = lambda r, s: s.get('atelier_mode', 'img2img')
    table(rows, 'mode', lambda r, s: (mode(r, s), s.get('generation_type', 'img2img')))
    table(rows, 'mode + model', lambda r, s: (mode(r, s), r['model_id']))
    table(rows, 'mode + cfg + denoise', lambda r, s: (mode(r, s), s.get('guidance_scale'), s.get('denoise')))
    table(rows, 'sampler + steps + scale', lambda r, s: (s.get('sampler'), s.get('steps'), s.get('scale')))
    table(rows, 'size', lambda r, s: (s.get('generation_width'), s.get('generation_height')))
    table(rows, 'colour level', lambda r, s: (mode(r, s), s.get('color_level')))
    table(rows, 'theme', lambda r, s: s.get('atelier_theme'))
    table(rows, 'recipe (new outputs only)', lambda r, s: (s.get('recipe') or {}).get('diffusers'), 1)
