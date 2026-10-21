"""Remove generated test samples (image, record, thumbnail) from the outputs Volume by exact markers.

Dry run by default:  .venv/bin/python -m modal run scripts/purge_test_outputs.py
Delete:              .venv/bin/python -m modal run scripts/purge_test_outputs.py --apply
A record is a test sample only if (a) its source_name is one of the markers the experiments used, or
(b) it is an Atelier image with a hand-picked seed below 2000 (the app draws random 32-bit seeds), or
(c) it is an img2img benchmark with seed 4242. Saved library images are never matched.
"""
import modal

app = modal.App('mulen-purge-test-outputs')
outputs = modal.Volume.from_name('img2img-outputs')
image = modal.Image.debian_slim(python_version='3.11')
MARKERS = {'palette-test', 'color-test', 'mixtest', 'smoke', 'mp', 'mt', 'style-test', 'bench'}


@app.function(image=image, volumes={'/outputs': outputs}, cpu=1, memory=1024, timeout=1800)
def purge(apply: bool = False, extra_markers: str = ''):
    import collections, json
    from pathlib import Path
    markers = MARKERS | {m for m in extra_markers.split(',') if m}
    out = Path('/outputs')
    outputs.reload()
    per_marker, other, victims = collections.Counter(), 0, []
    for record in out.glob('*.json'):
        try:
            data = json.loads(record.read_text())
        except Exception:
            continue
        if not isinstance(data, dict) or 'filename' not in data:
            continue
        settings = data.get('settings') or {}
        name = str(settings.get('source_name', ''))
        # img2img benchmark inputs were named after the uploaded file; they are tagged by their fixed seed
        seed = settings.get('seed')
        rule = None
        if name in markers:
            rule = name
        elif settings.get('generation_type') == 'atelier' and isinstance(seed, int) and 0 <= seed < 2000:
            rule = 'atelier-low-seed'
        elif name.startswith('source_') and seed == 4242:
            rule = 'img2img-benchmark'
        if rule and not data.get('saved_to_library'):
            per_marker[rule] += 1
            victims.append((record, data['filename']))
        else:
            other += 1
    removed = 0
    if apply:
        for record, filename in victims:
            for path in (out / filename, out / 'thumbs' / (Path(filename).stem + '.webp'), record):
                path.unlink(missing_ok=True)
            removed += 1
        outputs.commit()
    return {'would_remove' if not apply else 'removed': len(victims) if not apply else removed, 'by_marker': dict(per_marker), 'kept_other_records': other}


@app.local_entrypoint()
def main(apply: bool = False, extra: str = ''):
    import json
    print(json.dumps(purge.remote(apply, extra), indent=2))
