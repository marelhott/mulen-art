"""Single bounded GPU session: native resolution and deterministic VAE round trips."""
import io, json
from pathlib import Path
import modal
from modal_app import gpu_image, models, outputs

app = modal.App('img2img-native-detail-experiment')

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
    for size in [1024,1536,2048]:
        factor=size/max(source.size)
        dimensions=tuple(max(64,int(side*factor)//8*8) for side in source.size)
        resized=source.resize(dimensions,Image.Resampling.LANCZOS)
        image=pipe(prompt=settings['prompt'],negative_prompt=None,image=resized,strength=settings['denoise'],
                   guidance_scale=settings['guidance_scale'],num_inference_steps=settings['steps'],
                   generator=torch.Generator(device='cuda').manual_seed(settings['seed'])).images[0]
        save(f'native-{size}',image)
        if size==1536: baseline=image
        print(f'Native {dimensions} done',flush=True)
    # Diagnostic VAE run uses one consistent dtype; SDXL's selective upcast is decode-specific.
    pipe.unet.to('cpu')
    pipe.text_encoder.to('cpu'); pipe.text_encoder_2.to('cpu')
    core.clear_cuda()
    pipe.vae.to(dtype=torch.float32)
    tensor=pipe.image_processor.preprocess(baseline).to(device='cuda',dtype=pipe.vae.dtype)
    with torch.inference_mode():
        for tiled in [True,False]:
            if tiled: pipe.vae.enable_tiling()
            else: pipe.vae.disable_tiling()
            encoded=pipe.vae.encode(tensor).latent_dist.mode()
            decoded=pipe.vae.decode(encoded,return_dict=False)[0]
            image=pipe.image_processor.postprocess(decoded,output_type='pil')[0]
            save('vae-tiled' if tiled else 'vae-full',image)
            del encoded,decoded
            print(f'VAE round trip tiled={tiled} done',flush=True)
    return result

@app.local_entrypoint()
def main():
    folder=Path('outputs/verification/detail-native')
    settings=json.loads((folder/'input.json').read_text())['settings']
    for name,data in experiment.remote(settings).items(): (folder/f'{name}.png').write_bytes(data)
    print(f'Saved diagnostics to {folder}')
