"""Single bounded GPU session: native resolution and deterministic VAE round trips."""
import io, json
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-detail-1536-settings')

@app.function(image=gpu_image.add_local_python_source('modal_app'), volumes={'/models':models,'/published':outputs},
              gpu=['L4','A10G'], max_containers=1, timeout=300, retries=0)
def experiment(settings):
    from PIL import Image
    from app_runtime import core
    torch=core.get_torch()
    pipe=core.ensure_pipeline(settings['model_id'])
    pipe.scheduler=core.make_scheduler(pipe.scheduler.config,settings['sampler'],settings['schedule'])
    with Image.open(Path('/published')/Path(settings['source_url']).name) as raw:
        source=raw.convert('RGB')
    result={}
    def save(name,img):
        buffer=io.BytesIO();img.save(buffer,format='PNG');result[name]=buffer.getvalue()
    size = 1536
    factor = size / max(source.size)
    dimensions = tuple(max(64, int(side * factor) // 8 * 8) for side in source.size)
    resized = source.resize(dimensions, Image.Resampling.LANCZOS)
    for cfg, steps in [(3, 28), (5, 28), (3, 50), (5, 50)]:
        image = pipe(prompt=settings['prompt'], negative_prompt=None, image=resized,
                     strength=settings['denoise'], guidance_scale=cfg, num_inference_steps=steps,
                     generator=torch.Generator(device='cuda').manual_seed(settings['seed'])).images[0]
        save(f'cfg-{cfg}-steps-{steps}', image)
        print(f'CFG {cfg}, schedule {steps} steps done', flush=True)
    return result

@app.local_entrypoint()
def main():
    folder=Path('outputs/verification/detail-native')
    settings=json.loads((folder/'input.json').read_text())['settings']
    target=Path('outputs/verification/detail-settings-1536'); target.mkdir(parents=True, exist_ok=True)
    for name,data in experiment.remote(settings).items(): (target/f'{name}.png').write_bytes(data)
    print(f'Saved diagnostics to {folder}')
