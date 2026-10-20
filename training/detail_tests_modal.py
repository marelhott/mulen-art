"""Private high-resolution inference tests; no training and no output enhancement."""
import json
from pathlib import Path
import modal
app=modal.App('mulen-sdxl-detail-tests')
models=modal.Volume.from_name('img2img-models')
sources=modal.Volume.from_name('img2img-outputs')
results=modal.Volume.from_name('mulen-training-results')
image=(modal.Image.debian_slim(python_version='3.11')
 .pip_install('torch==2.5.1','torchvision==0.20.1','diffusers==0.32.2','transformers==4.48.0','accelerate==1.2.1','peft==0.14.0','safetensors==0.5.2','pillow==11.1.0','sentencepiece==0.2.0','protobuf==5.29.3','xformers==0.0.28.post3','fastapi==0.115.6')
 .env({'HF_HOME':'/models/huggingface-cache','TOKENIZERS_PARALLELISM':'false'})
 .add_local_python_source('app_runtime'))

@app.function(image=image,gpu='L4',cpu=2,memory=24576,timeout=3600,max_containers=1,retries=0,
 volumes={'/models':models,'/sources':sources,'/results':results})
def run_tests(run_id:str,inputs:list[dict]):
 import gc,time,traceback,torch
 from PIL import Image,ImageOps,PngImagePlugin
 from diffusers import StableDiffusionXLImg2ImgPipeline
 from app_runtime.core import make_scheduler
 if not run_id.startswith('detail-tests-') or '/' in run_id or len(inputs)!=12:raise ValueError('Invalid bounded experiment')
 folder=Path('/results')/run_id;folder.mkdir(exist_ok=True)
 status={'run_id':run_id,'phase':'running','expected_outputs':108,'completed_outputs':0,'inputs':inputs,'started_unix':time.time(),'settings':{'prompt':'','negative_prompt':None,'cfg':.5,'steps':28,'seed':231020,'denoise':[.50,.55],'sampler':'dpmpp_2m','schedule':'karras','native_max_edges':[1024,1536],'postprocess':'none','note':'Larger diffusion canvas can change composition/style; 1024 controls are included.'}}
 def save():
  (folder/'status.json').write_text(json.dumps(status,indent=2));results.commit()
 save()
 base=Path('/results/full-unet-approved-20261019T203404Z')
 variants=[('2400',base/'mvhpaint_full_unet-step00002400.safetensors'),('800',base/'mvhpaint_full_unet-step00000800.safetensors'),('1600',base/'mvhpaint_full_unet-step00001600.safetensors'),('dreamlook',Path('/models/checkpoints/Tuymans_SDXL.safetensors'))]
 prepared={};records=[];start=time.monotonic()
 try:
  for item in inputs:
   name=item['path'];index=item['index']
   if Path(name).name!=name or not name.startswith('source_'):raise ValueError('Invalid private source')
   with Image.open(Path('/sources')/name) as raw:original=ImageOps.exif_transpose(raw).convert('RGB')
   original.save(folder/f'input-{index:02d}-original.png')
   for edge in [1024,1536]:
    factor=edge/max(original.size);w=max(64,int(original.width*factor)//8*8);h=max(64,int(original.height*factor)//8*8)
    im=original.resize((w,h),Image.Resampling.LANCZOS);prepared[index,edge]=im
    im.save(folder/f'input-{index:02d}-{edge}.png')
  save()
  for label,checkpoint in variants:
   if not checkpoint.is_file():raise FileNotFoundError(checkpoint)
   pipe=StableDiffusionXLImg2ImgPipeline.from_single_file(str(checkpoint),torch_dtype=torch.float16,use_safetensors=True).to('cuda')
   pipe.enable_vae_tiling();pipe.enable_xformers_memory_efficient_attention()
   for item in inputs:
    index=item['index']
    configs=[(1536,.55)] if label=='dreamlook' else [(1536,.50),(1536,.55)]+([(1024,.55)] if label in {'800','2400'} else [])
    for edge,strength in configs:
     name=f'input-{index:02d}-{label}-{edge}-d{int(strength*100)}';png=folder/(name+'.png');sidecar=folder/(name+'.json')
     # Resume only complete, matching samples after platform preemption.
     if png.exists() and sidecar.exists():
      record=json.loads(sidecar.read_text())
      with Image.open(png) as check:check.verify()
      records.append(record);status['completed_outputs']=len(records);continue
     im=prepared[index,edge];pipe.scheduler=make_scheduler(pipe.scheduler.config,'dpmpp_2m','karras')
     begin=time.monotonic()
     output=pipe(prompt='',negative_prompt=None,image=im,strength=strength,guidance_scale=.5,num_inference_steps=28,generator=torch.Generator('cuda').manual_seed(231020)).images[0]
     record={'file':png.name,'input_index':index,'label':item['label'],'checkpoint':str(checkpoint),'variant':label,'max_edge':edge,'size':list(output.size),'denoise':strength,'cfg':.5,'steps':28,'seed':231020,'prompt':'','negative_prompt':None,'guidance_active':bool(pipe.do_classifier_free_guidance),'elapsed_seconds':round(time.monotonic()-begin,3),'postprocess':'none'}
     info=PngImagePlugin.PngInfo();info.add_text('test_parameters',json.dumps(record))
     output.save(png,pnginfo=info);sidecar.write_text(json.dumps(record,indent=2));records.append(record)
     status['completed_outputs']=len(records);status['current_variant']=label
     if len(records)%4==0:save()
   del pipe;gc.collect();torch.cuda.empty_cache();save()
  assert len(records)==108
  (folder/'manifest.json').write_text(json.dumps(records,indent=2))
  status.update(phase='completed',elapsed_seconds=round(time.monotonic()-start,2),finished_unix=time.time());save();return status
 except BaseException:
  status.update(phase='interrupted_or_failed',error=traceback.format_exc());save();raise

@app.local_entrypoint()
def main():
 from datetime import datetime,timezone
 records=json.loads((Path(__file__).resolve().parents[1]/'outputs/research/tuymans/source-inputs.json').read_text())
 labels={1:'Headdress portrait',4:'Sculptural torso',6:'Seated figure',7:'Reclining painted figure',9:'Soft portrait',11:'Figure with glowing spots',13:'Figure in green space',14:'Striped portrait',15:'Dark male portrait',17:'Red garment figure',20:'Face behind branches',21:'Soft standing figure'}
 selected=[{**records[i],'index':i,'label':label} for i,label in labels.items()]
 run_id='detail-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 local=Path(__file__).resolve().parents[1]/'outputs/research/tuymans';(local/'detail-tests-active.json').write_text(json.dumps({'run_id':run_id,'expected_outputs':108},indent=2))
 print(json.dumps(run_tests.remote(run_id,selected),indent=2))
