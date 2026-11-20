"""Bounded visual comparison: one existing painting and one gentle SDXL detail pass."""
import io
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-detail-experiment')

@app.function(image=gpu_image.add_local_python_source('modal_app'), volumes={'/models': models, '/published': outputs},
              gpu=['L4', 'A10G'], max_containers=1, timeout=420, retries=0)
def compare(filename):
    from PIL import Image
    from app_runtime import core
    from app_runtime.atelier import painting_prompt
    with Image.open(Path('/published') / Path(filename).name) as img:
        base = img.convert('RGB')
    base.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    target = core.detail_dimensions(base.size, 1.5)
    before = base.resize(target, Image.Resampling.LANCZOS)
    pipe = core.ensure_pipeline('tuymans_modal_2400')
    core.ensure_lora(pipe, 'none', 0)
    pipe.scheduler = core.make_scheduler(pipe.scheduler.config, 'dpmpp_2m', 'karras')
    steps, strength = core.inference_schedule(10, .30, True)
    after = pipe(prompt=painting_prompt('tuymans_modal_2400', '').rstrip(', '), negative_prompt=None,
                 image=before, strength=strength, guidance_scale=3.0, num_inference_steps=steps,
                 generator=core.get_torch().Generator(device='cuda').manual_seed(2284341393)).images[0]
    def png(image):
        out=io.BytesIO(); image.save(out, format='PNG'); return out.getvalue()
    return png(before), png(after)

@app.local_entrypoint()
def main():
    target=Path('outputs/verification/detail-experiment'); target.mkdir(parents=True, exist_ok=True)
    before, after=compare.remote('20261024T155251356031_01_tuymans_modal_2400.png')
    (target/'before-atelier.png').write_bytes(before); (target/'after-atelier-030.png').write_bytes(after)
    print(f'Comparison saved in {target}')
