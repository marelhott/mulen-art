"""Keep the original latent through upscale, avoiding a second VAE encode."""
import io,json
from pathlib import Path
import modal
from modal_app import gpu_image,models,outputs
app=modal.App('img2img-latent-detail-experiment')
@app.function(image=gpu_image.add_local_python_source('modal_app'),volumes={'/models':models,'/published':outputs},
              gpu=['L4','A10G'],max_containers=1,timeout=300,retries=0)
def compare(s):
    from PIL import Image
    from app_runtime import core
    torch=core.get_torch();pipe=core.ensure_pipeline(s['model_id'])
    pipe.scheduler=core.make_scheduler(pipe.scheduler.config,s['sampler'],s['schedule'])
    with Image.open(Path('/published')/Path(s['source_url']).name) as raw: source=raw.convert('RGB')
    ratio=1536/max(source.size);source=source.resize(tuple(int(x*ratio)//8*8 for x in source.size),Image.Resampling.LANCZOS)
    gen=lambda:torch.Generator(device='cuda').manual_seed(s['seed'])
    latent=pipe(prompt=s['prompt'],negative_prompt=None,image=source,strength=s['denoise'],guidance_scale=s['guidance_scale'],
                num_inference_steps=s['steps'],generator=gen(),output_type='latent').images
    enlarged=torch.nn.functional.interpolate(latent,size=(191,256),mode='bicubic',align_corners=False)
    steps,strength=core.inference_schedule(10,.18,True)
    refined=pipe(prompt=s['prompt'],negative_prompt=None,image=enlarged,strength=strength,guidance_scale=s['guidance_scale'],
                 num_inference_steps=steps,generator=gen()).images[0]
    pipe.unet.to('cpu');pipe.text_encoder.to('cpu');pipe.text_encoder_2.to('cpu');core.clear_cuda();pipe.vae.to(dtype=torch.float32)
    with torch.inference_mode():
        decoded=pipe.vae.decode(latent.float()/pipe.vae.config.scaling_factor,return_dict=False)[0]
        original=pipe.image_processor.postprocess(decoded,output_type='pil')[0]
    def png(img):
        b=io.BytesIO();img.save(b,format='PNG');return b.getvalue()
    return png(original),png(refined)
@app.local_entrypoint()
def main():
    p=Path('outputs/verification/detail-native');s=json.loads((p/'input.json').read_text())['settings']
    base,detail=compare.remote(s);(p/'latent-base.png').write_bytes(base);(p/'latent-refined.png').write_bytes(detail)
