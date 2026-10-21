"""Private reference archives, separate from checkpoint weights."""
import hashlib
import json
import os
import random
from pathlib import Path


def archive_root():
    return Path(os.environ.get('ARCHIVE_ROOT', str(Path(os.environ.get('OUTPUTS_DIR', '/outputs')) / 'atelier-archives')))


def load_manifest():
    path = archive_root() / 'manifest.json'
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {'archives': []}


def archive_options():
    return [{k: a[k] for k in ('id', 'name', 'count')} for a in load_manifest()['archives']]


def reference_for(archive_id, seed):
    archive = next((a for a in load_manifest()['archives'] if a['id'] == archive_id), None)
    if not archive or not archive.get('items'):
        raise ValueError('Reference archive is unavailable or empty')
    # Shuffle in cycles: consecutive study seeds cover the archive before repeating.
    items = list(archive['items'])
    cycle, index = divmod(seed, len(items))
    random.Random(f'{archive_id}:{cycle}').shuffle(items)
    item = items[index]
    root = archive_root().resolve()
    path = (root / item['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Reference file is unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Reference integrity check failed')
    return archive, item, path


def generate_reference(spec, progress, image_callback):
    import base64
    from PIL import Image, ImageOps
    from . import core
    from .server import OUTPUTS_DIR
    images, final_meta = [], {}
    for index in range(spec.num_images):
        seed = random.randint(0, 2**32 - 1) if spec.seed == -1 else (spec.seed + index) % 2**32
        archive, item, path = reference_for(spec.atelier_archive, seed)
        with Image.open(path) as raw:
            source = ImageOps.exif_transpose(raw).convert('RGB')
        source.thumbnail((spec.width, spec.height), Image.Resampling.LANCZOS)
        source = core.prepare_source(source, 1, max(spec.width, spec.height))
        source_data = core.encode_image(source, {})
        source_name = 'source_archive_' + hashlib.sha256(base64.b64decode(source_data['image_base64'])).hexdigest() + '.png'
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUTS_DIR / source_name).write_bytes(base64.b64decode(source_data['image_base64']))
        provenance = {'generation_type': 'atelier', 'atelier_mode': 'archive',
            'atelier_archive': archive['id'], 'archive_name': archive['name'],
            'reference_id': item['id'], 'reference_filename': item['filename'],
            'reference_sha256': item['sha256'], 'subject_origin': 'reference-archive',
            'subject_title': archive['name'] + ' · ' + item['filename'],
            'source_name': item['filename'], 'source_url': '/library/' + source_name,
            'prompt': '', 'negative_prompt': '', 'cfg': spec.cfg}
        def ready(image, meta):
            nonlocal final_meta
            # Provenance was already embedded by generate(extra_meta=...); no PNG re-encode.
            final_meta = {**meta, **provenance}
            encoded = {**image, 'generation_meta': final_meta}
            images.append(encoded)
            if image_callback:
                image_callback(encoded, final_meta)
        def report(value, message):
            core.report_progress(progress, (index + value) / spec.num_images, 'Archiv · ' + message)
        result = core.generate({'generation_type':'img2img', 'image_base64':source_data['image_base64'],
            'model_id':spec.model_id, 'lora_id':'none', 'seed':seed, 'denoise':spec.denoise,
            'cfg':spec.cfg, 'steps':spec.steps, 'sampler':spec.sampler, 'schedule':spec.schedule,
            'scale':spec.scale, 'num_images':1, 'render_mode':'quick', 'conditioning_mode':'style',
            'prompt':'', 'negative_prompt':'', 'max_side':max(spec.width,spec.height)}, report, ready, extra_meta=provenance)
    return {'images':images, 'meta':final_meta}
