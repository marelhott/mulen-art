"""Private reference archives, separate from checkpoint weights."""
import hashlib
import json
import os
import random
from functools import lru_cache
from pathlib import Path


def archive_root():
    return Path(os.environ.get('ARCHIVE_ROOT', str(Path(os.environ.get('OUTPUTS_DIR', '/outputs')) / 'atelier-archives')))


def load_manifest():
    # Parsed once per (mtime, size): one atelier request used to re-parse it for every study it planned.
    path = archive_root() / 'manifest.json'
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {'archives': []}
    return _load_manifest(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _load_manifest(path, _mtime_ns, _size):
    return json.loads(Path(path).read_text())


def archive_options():
    return [{k: a[k] for k in ('id', 'name', 'count')} for a in load_manifest()['archives']]


def pick_reference(archive_id, seed):
    """Choose the reference for a seed from the manifest alone (no file access) - enough to title a study."""
    archive = next((a for a in load_manifest()['archives'] if a['id'] == archive_id), None)
    if not archive or not archive.get('items'):
        raise ValueError('Reference archive is unavailable or empty')
    # Shuffle in cycles: consecutive study seeds cover the archive before repeating.
    items = list(archive['items'])
    cycle, index = divmod(seed, len(items))
    random.Random(f'{archive_id}:{cycle}').shuffle(items)
    return archive, items[index]


def reference_for(archive_id, seed):
    archive, item = pick_reference(archive_id, seed)
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
        source = core.prepare_source(source, spec.input_scale, max(spec.width, spec.height, 1008))
        source_data = core.encode_image(source, {}, 'PNG')  # the file below is named .png whatever OUTPUT_FORMAT says
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
        def report(value, message):
            core.report_progress(progress, (index + value) / spec.num_images, 'Archiv · ' + message)
        from .repaint import repaint
        result, repaint_meta = repaint(source, spec, seed, report)
        result, actual_upscaler = core.apply_output_upscaler(result, spec.scale, spec.use_realsrgan, spec.output_upscaler, spec.restormer_mode)
        final_meta = {**provenance, **repaint_meta,
            'model_id': spec.model_id, 'model_name': core.get_config_item('models', spec.model_id)['name'],
            'lora_id': 'none', 'seed': seed, 'sampler': spec.sampler, 'schedule': spec.schedule,
            'generation_width': source.width, 'generation_height': source.height,
            'output_width': result.width, 'output_height': result.height,
            'scale': spec.scale, 'upscaler': actual_upscaler, 'restormer_mode': spec.restormer_mode, 'render_mode': 'quick', 'demo_mode': False}
        encoded = {**core.encode_image(result, final_meta), 'generation_meta': final_meta}
        images.append(encoded)
        if image_callback:
            image_callback(encoded, final_meta)
        report(1, 'Obraz uložen')
    return {'images':images, 'meta':final_meta}
