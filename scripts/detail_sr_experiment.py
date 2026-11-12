"""Bounded SwinIR classical reconstruction SR comparison. No production jobs or model changes."""
import hashlib,io,json
from pathlib import Path
import modal

ROOT=Path(__file__).resolve().parents[1]
INPUTS=ROOT/'outputs/verification/sr-inputs'
app=modal.App('img2img-reconstruction-sr-experiment')
image=(modal.Image.debian_slim(python_version='3.11')
       .pip_install_from_requirements(str(ROOT/'app_runtime/requirements.txt'))
       .pip_install('spandrel==0.4.1').add_local_dir(str(INPUTS),'/experiment-inputs'))

@app.function(image=image,gpu=['L4','A10G'],max_containers=1,timeout=420,retries=0)
def experiment():
    import urllib.request,time
    import numpy as np
    import torch
    from PIL import Image
    from spandrel import ModelLoader,ImageModelDescriptor
    start=time.monotonic()
    url='https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/001_classicalSR_DF2K_s64w8_SwinIR-M_x2.pth'
    checkpoint=Path('/tmp/swinir-classical-x2.pth')
    urllib.request.urlretrieve(url,checkpoint)
    model=ModelLoader().load_from_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True))
    assert isinstance(model,ImageModelDescriptor) and model.scale==2
    model.cuda().eval()
    results={}
    for path in sorted(Path('/experiment-inputs').glob('*.png')):
        src=Image.open(path).convert('RGB');width,height=src.size
        tensor=torch.from_numpy(np.asarray(src).copy()).permute(2,0,1).unsqueeze(0).float()/255
        output=torch.empty((1,3,height*2,width*2),dtype=torch.float32)
        tile,pad=384,32
        with torch.inference_mode():
            for y in range(0,height,tile):
                for x in range(0,width,tile):
                    x1,y1=max(0,x-pad),max(0,y-pad)
                    x2,y2=min(width,x+tile+pad),min(height,y+tile+pad)
                    patch=model(tensor[:,:,y1:y2,x1:x2].cuda()).cpu()
                    outw,outh=min(tile,width-x)*2,min(tile,height-y)*2
                    output[:,:,y*2:y*2+outh,x*2:x*2+outw]=patch[:,:,(y-y1)*2:(y-y1)*2+outh,(x-x1)*2:(x-x1)*2+outw]
        array=output.squeeze(0).clamp(0,1).permute(1,2,0).mul(255).round().byte().numpy()
        buffer=io.BytesIO();Image.fromarray(array).save(buffer,format='PNG');results[path.stem]=buffer.getvalue()
        print(f'{path.name}: {src.size} -> {width*2,height*2}, elapsed {time.monotonic()-start:.1f}s',flush=True)
    return results,{'checkpoint_url':url,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                    'tile':tile,'context':pad,'seconds':time.monotonic()-start}

@app.local_entrypoint()
def main():
    target=ROOT/'outputs/verification/detail-sr';target.mkdir(parents=True,exist_ok=True)
    results,meta=experiment.remote()
    for name,data in results.items(): (target/f'{name}-swinir.png').write_bytes(data)
    (target/'run.json').write_text(json.dumps(meta,indent=2))
    print(f'Saved comparisons to {target}')
