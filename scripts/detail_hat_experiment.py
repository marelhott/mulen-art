"""Compare real-world SwinIR PSNR and GAN on matched 512px painting patches."""
import io,json,hashlib
from pathlib import Path
import modal
ROOT=Path(__file__).resolve().parents[1]
app=modal.App('img2img-hat-comparison')
image=(modal.Image.debian_slim(python_version='3.11').pip_install_from_requirements(str(ROOT/'app_runtime/requirements.txt'))
       .pip_install('spandrel==0.4.1').add_local_dir(str(ROOT/'outputs/verification/sr-patches'),'/patches').add_local_python_source('app_runtime'))
@app.function(image=image,gpu=['L4','A10G'],timeout=600,max_containers=1,retries=0)
def compare():
    import urllib.request
    import numpy as np,torch
    from PIL import Image
    from spandrel import ModelLoader
    from app_runtime import realsrgan
    results={};meta={}
    for kind in ['Real_HAT_GAN_sharper']:
        filename=kind+'.pth'
        url='https://huggingface.co/anchuang/Real_HAT_GAN_SRx4_sharper/resolve/4d7eb31975e6a8f26f3d2c474ebc1515924149c6/'+filename
        target=Path('/tmp')/filename;urllib.request.urlretrieve(url,target)
        model=ModelLoader().load_from_state_dict(torch.load(target,map_location='cpu',weights_only=True)).cuda().eval()
        assert model.scale==4
        meta[kind]={'url':url,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        for path in sorted(Path('/patches').glob('*.png')):
            picture=Image.open(path).convert('RGB')
            realsrgan._MODEL=model
            result=realsrgan.upscale(picture).resize((picture.width*2,picture.height*2),Image.Resampling.LANCZOS)
            b=io.BytesIO();result.save(b,format='PNG');results[f'{path.stem}-{kind}']=b.getvalue()
            print(f'{path.name} {kind} done',flush=True)
        realsrgan._MODEL=None; del model;torch.cuda.empty_cache()
    return results,meta
@app.local_entrypoint()
def main():
    p=ROOT/'outputs/verification/detail-hat';p.mkdir(parents=True,exist_ok=True)
    images,meta=compare.remote()
    for name,data in images.items():(p/f'{name}.png').write_bytes(data)
    (p/'models.json').write_text(json.dumps(meta,indent=2))
