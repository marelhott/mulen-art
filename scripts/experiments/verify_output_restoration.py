"""Bounded GPU check: generate one sample with both optional restoration models."""
import base64
from pathlib import Path
import modal
from modal_app import gpu_image, models

ROOT = Path(__file__).resolve().parents[2]
app = modal.App('img2img-output-restoration-smoke')
image = gpu_image.add_local_python_source('modal_app').add_local_dir(str(ROOT / 'outputs/verification/sr-patches'), '/patches')


@app.function(image=image, gpu=['L4', 'A10G'], volumes={'/models': models}, timeout=600, max_containers=1, retries=0)
def verify():
    import io
    from PIL import Image
    from app_runtime import core
    from app_runtime.restormer import deblur
    raw = Path('/patches/canvas.png').read_bytes()
    payload = {'image_base64': base64.b64encode(raw).decode(), 'model_id': 'tuymans_modal_2400',
               'seed': 42, 'steps': 5, 'denoise': 0.5, 'cfg': 5, 'scale': 2, 'max_side': 1024,
               'output_upscaler': 'realesrgan', 'restormer_mode': 'defocus'}
    result = core.generate(payload)
    image = result['images'][0]
    with Image.open(io.BytesIO(raw)) as sample:
        motion = deblur(sample.convert('RGB'), 'motion')
    return image['image_base64'], image['generation_meta'], motion.size


@app.local_entrypoint()
def main():
    data, meta, motion_size = verify.remote()
    target = ROOT / 'outputs/verification/detail-output-restoration-smoke.png'
    target.write_bytes(base64.b64decode(data))
    print({'output_size': (meta['output_width'], meta['output_height']),
           'upscaler': meta['upscaler'], 'restormer': meta['restormer_mode'],
           'motion_size': motion_size, 'file': str(target)})
