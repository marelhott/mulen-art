"""Artist detail synthesis on small patches, evaluated only as constrained high-pass residuals."""
import io
from pathlib import Path
import modal
from modal_app import gpu_image,models
ROOT=Path(__file__).resolve().parents[1]
app=modal.App('img2img-artist-patch-detail-experiment')
image=gpu_image.add_local_python_source('modal_app').add_local_dir(str(ROOT/'outputs/verification/sr-patches'),'/patches')
@app.function(image=image,volumes={'/models':models},gpu=['L4','A10G'],timeout=180,max_containers=1,retries=0)
def compare():
    from PIL import Image
    from app_runtime import core
    from app_runtime.atelier import painting_prompt
    torch=core.get_torch();pipe=core.ensure_pipeline('tuymans_modal_2400')
    pipe.scheduler=core.make_scheduler(pipe.scheduler.config,'dpmpp_2m','karras')
    steps,strength=core.inference_schedule(10,.30,True);results={}
    for path in sorted(Path('/patches').glob('*.png')):
        source=Image.open(path).convert('RGB').resize((1024,1024),Image.Resampling.LANCZOS)
        output=pipe(prompt=painting_prompt('tuymans_modal_2400','').rstrip(', '),negative_prompt=None,
                    image=source,strength=strength,guidance_scale=3,num_inference_steps=steps,
                    generator=torch.Generator(device='cuda').manual_seed(2284341393)).images[0]
        b=io.BytesIO();output.save(b,format='PNG');results[path.stem]=b.getvalue()
    return results
@app.local_entrypoint()
def main():
    p=ROOT/'outputs/verification/detail-patch';p.mkdir(parents=True,exist_ok=True)
    for name,data in compare.remote().items():(p/f'{name}-raw.png').write_bytes(data)
