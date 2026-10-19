"""Controlled private comparison using the deployed app's inference environment."""
import json
from pathlib import Path
import modal
gpu_image=(modal.Image.debian_slim(python_version='3.11')
    .pip_install('torch==2.5.1','torchvision==0.20.1','diffusers==0.32.2',
                 'transformers==4.48.0','accelerate==1.2.1','peft==0.14.0',
                 'safetensors==0.5.2','pillow==11.1.0','sentencepiece==0.2.0',
                 'protobuf==5.29.3','xformers==0.0.28.post3','fastapi==0.115.6')
    .env({'HF_HOME':'/models/huggingface-cache','TOKENIZERS_PARALLELISM':'false'})
    .add_local_python_source('app_runtime'))

app=modal.App('mulen-sdxl-evaluation')
models=modal.Volume.from_name('img2img-models')
sources=modal.Volume.from_name('img2img-outputs')
results=modal.Volume.from_name('mulen-training-results')

@app.function(image=gpu_image, gpu='L4', cpu=2, memory=24576,
              volumes={'/models':models,'/sources':sources,'/results':results},
              timeout=1800,max_containers=1,retries=0)
def compare(adapter_path: str, source_files: list[str]):
    import time,gc
    import torch
    from PIL import Image, ImageOps
    from diffusers import StableDiffusionXLImg2ImgPipeline
    from app_runtime.core import make_scheduler
    if len(source_files)>8: raise ValueError('Evaluation should be a bounded representative sample')
    adapter=Path('/results')/adapter_path
    if not adapter.is_file() or adapter.suffix!='.safetensors': raise ValueError('Missing trained adapter')
    folder=adapter.parent/'comparison';folder.mkdir(exist_ok=True)
    metadata={'adapter':adapter_path,'prompt':'','negative_prompt':None,'cfg':1.8,
              'steps':28,'seed':231019,'sampler':'dpmpp_2m','schedule':'karras',
              'conditioning':'empty positive, zero unconditional; same as app style mode',
              'source_files':source_files,'images':[]}
    start=time.monotonic()
    for label,checkpoint,use_adapter in [
        ('dreamlook','Tuymans_SDXL.safetensors',False),
        ('base','sd_xl_base_1.0.safetensors',False),
        ('pilot','sd_xl_base_1.0.safetensors',True),
    ]:
        pipe=StableDiffusionXLImg2ImgPipeline.from_single_file(
            '/models/checkpoints/'+checkpoint,torch_dtype=torch.float16,use_safetensors=True).to('cuda')
        pipe.enable_vae_tiling()
        try: pipe.enable_xformers_memory_efficient_attention()
        except Exception: pass
        if use_adapter: pipe.load_lora_weights(str(adapter))
        for i,name in enumerate(source_files):
            # Strict filename-only source selection; preserve the private originals.
            if Path(name).name!=name or not name.startswith('source_'): raise ValueError('Invalid source')
            with Image.open(Path('/sources')/name) as raw:
                im=ImageOps.exif_transpose(raw).convert('RGB'); im.thumbnail((1024,1024),Image.Resampling.LANCZOS)
                im=im.resize((max(64,im.width//8*8),max(64,im.height//8*8)),Image.Resampling.LANCZOS)
            if label=='dreamlook': im.save(folder/f'{i:02d}-source.png')
            for denoise in [.52,.70]:
                pipe.scheduler=make_scheduler(pipe.scheduler.config,'dpmpp_2m','karras')
                output=pipe(prompt='',negative_prompt=None,image=im,strength=denoise,
                    guidance_scale=1.8,num_inference_steps=28,
                    generator=torch.Generator('cuda').manual_seed(231019)).images[0]
                name_out=f'{i:02d}-{label}-d{int(denoise*100)}.png';output.save(folder/name_out)
                metadata['images'].append({'file':name_out,'source_index':i,'model':label,'denoise':denoise})
        del pipe;gc.collect();torch.cuda.empty_cache()
        (folder/'metadata.json').write_text(json.dumps(metadata,indent=2));results.commit()
    metadata['elapsed_seconds']=round(time.monotonic()-start,2)
    (folder/'metadata.json').write_text(json.dumps(metadata,indent=2));results.commit()
    return metadata

@app.function(image=gpu_image, gpu='L4', cpu=2, memory=24576,
              volumes={'/models':models,'/sources':sources,'/results':results},
              timeout=1800,max_containers=1,retries=0)
def evaluate_checkpoint(checkpoint_path: str, source_files: list[str]):
    import time, torch
    from PIL import Image, ImageOps
    from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLPipeline
    from app_runtime.core import make_scheduler
    checkpoint=Path('/results')/checkpoint_path
    if not checkpoint.is_file() or checkpoint.suffix!='.safetensors' or '..' in Path(checkpoint_path).parts:
        raise ValueError('Missing or invalid full checkpoint')
    if not 1 <= len(source_files) <= 8: raise ValueError('Invalid evaluation size')
    folder=checkpoint.parent/('evaluation-'+checkpoint.stem);folder.mkdir(exist_ok=True)
    meta={'checkpoint':checkpoint_path,'prompt':'','negative_prompt':None,'cfg':1.8,
          'steps':28,'seed':231019,'sampler':'dpmpp_2m','schedule':'karras',
          'source_files':source_files,'images':[]}
    start=time.monotonic()
    pipe=StableDiffusionXLImg2ImgPipeline.from_single_file(str(checkpoint),
        torch_dtype=torch.float16,use_safetensors=True).to('cuda')
    pipe.enable_vae_tiling()
    try: pipe.enable_xformers_memory_efficient_attention()
    except Exception: pass
    for i,name in enumerate(source_files):
        if Path(name).name!=name or not name.startswith('source_'): raise ValueError('Invalid source')
        with Image.open(Path('/sources')/name) as raw:
            im=ImageOps.exif_transpose(raw).convert('RGB');im.thumbnail((1024,1024),Image.Resampling.LANCZOS)
            im=im.resize((max(64,im.width//8*8),max(64,im.height//8*8)),Image.Resampling.LANCZOS)
        im.save(folder/f'{i:02d}-source.png')
        for denoise in [.52,.70]:
            pipe.scheduler=make_scheduler(pipe.scheduler.config,'dpmpp_2m','karras')
            output=pipe(prompt='',negative_prompt=None,image=im,strength=denoise,
                guidance_scale=1.8,num_inference_steps=28,
                generator=torch.Generator('cuda').manual_seed(231019)).images[0]
            name_out=f'{i:02d}-full-d{int(denoise*100)}.png';output.save(folder/name_out)
            meta['images'].append({'file':name_out,'source_index':i,'denoise':denoise})
    txt=StableDiffusionXLPipeline(**pipe.components)
    contents=['a small empty room with a single chair beside a window',
              'a frontal portrait of a middle-aged person in a plain shirt',
              'a country road with a few distant trees',
              'a ceramic bowl and a drinking glass on a table',
              'a bird sitting on a bare branch',
              'an empty building facade seen from across a street']
    for i,content in enumerate(contents):
        prompt='mvhpaint, '+content
        txt.scheduler=make_scheduler(txt.scheduler.config,'dpmpp_2m','karras')
        im=txt(prompt=prompt,negative_prompt=None,width=1024,height=1024,guidance_scale=5,
               num_inference_steps=28,generator=torch.Generator('cuda').manual_seed(91230+i)).images[0]
        im.save(folder/f'txt-{i:02d}.png')
    meta['text_test_contents']=contents
    meta['elapsed_seconds']=round(time.monotonic()-start,2)
    (folder/'metadata.json').write_text(json.dumps(meta,indent=2));results.commit()
    return meta

@app.function(image=gpu_image, gpu='L4', cpu=2, memory=24576,
              volumes={'/models':models,'/data':modal.Volume.from_name('mulen-training-data')},
              timeout=900,max_containers=1,retries=0)
def make_regularization():
    import torch, time
    from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler
    from pathlib import Path
    data=modal.Volume.from_name('mulen-training-data')
    folder=Path('/data/dataset-v1/regularization');folder.mkdir(exist_ok=True)
    subjects=[
        'a portrait of a middle-aged man in a plain collared shirt',
        'a portrait of a woman with short dark hair',
        'a small empty bedroom with a bed and a wooden chair',
        'a quiet room with a desk beside a window',
        'a country road through trees and fields',
        'a distant house beside a wooded hillside',
        'a glass and a ceramic bowl on a plain table',
        'a small potted plant against a wall',
        'a pale bird sitting on a branch',
        'a rabbit sitting beside some leaves',
        'a person standing alone beside a building',
        'a sailing boat on still water']
    pipe=StableDiffusionXLPipeline.from_single_file('/models/checkpoints/sd_xl_base_1.0.safetensors',
        torch_dtype=torch.float16,use_safetensors=True).to('cuda')
    pipe.scheduler=DPMSolverMultistepScheduler.from_config(pipe.scheduler.config,use_karras_sigmas=True)
    start=time.monotonic()
    for i,subject in enumerate(subjects):
        caption='an oil painting of '+subject
        output=pipe(prompt=caption,negative_prompt=None,width=1024,height=1024,
            num_inference_steps=28,guidance_scale=5,
            generator=torch.Generator('cuda').manual_seed(91200+i)).images[0]
        output.save(folder/f'reg_{i:02d}.png')
        (folder/f'reg_{i:02d}.txt').write_text(caption+'\n')
    metadata={'base':'sd_xl_base_1.0.safetensors','subjects':subjects,'seed_start':91200,
              'steps':28,'cfg':5,'resolution':1024,'elapsed_seconds':time.monotonic()-start,
              'purpose':'small generic painting prior replay; no artist trigger'}
    (folder/'generation.json').write_text(json.dumps(metadata,indent=2));data.commit()
    return metadata

@app.local_entrypoint()
def main(adapter_path: str = '', regularization: bool = False, checkpoint_path: str = ''):
    if regularization:
        print(json.dumps(make_regularization.remote(),indent=2));return
    records=json.loads((Path(__file__).resolve().parents[1]/'outputs/research/tuymans/source-inputs.json').read_text())
    selected=[records[i]['path'] for i in [0,10,12,16,18,19]]
    result=evaluate_checkpoint.remote(checkpoint_path,selected) if checkpoint_path else compare.remote(adapter_path,selected)
    print(json.dumps(result,indent=2))
