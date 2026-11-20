"""Compare real-world SwinIR PSNR and GAN on matched 512px painting patches."""
import io,json,hashlib
from pathlib import Path
import modal
ROOT=Path(__file__).resolve().parents[2]
app=modal.App('img2img-restormer-deblur-experiment')
image=(modal.Image.debian_slim(python_version='3.11').pip_install_from_requirements(str(ROOT/'app_runtime/requirements.txt'))
       .pip_install('spandrel==0.4.1').add_local_dir(str(ROOT/'outputs/verification/sr-patches'),'/patches'))
@app.function(image=image,gpu=['L4','A10G'],timeout=300,max_containers=1,retries=0)
def compare():
    import urllib.request
    import numpy as np,torch
    from PIL import Image
    from spandrel import ModelLoader
    results={};meta={}
    for kind in ['motion_deblurring', 'single_image_defocus_deblurring']:
        filename=kind+'.pt'
        url='https://huggingface.co/spaces/swzamir/Restormer/resolve/main/'+filename
        target=Path('/tmp')/filename;urllib.request.urlretrieve(url,target)
        model=torch.jit.load(str(target),map_location='cpu').cuda().eval()
        meta[kind]={'url':url,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        for path in sorted(Path('/patches').glob('*.png')):
            picture=Image.open(path).convert('RGB');array=np.asarray(picture).copy()
            tensor=torch.from_numpy(array).permute(2,0,1).unsqueeze(0).float().cuda()/255
            with torch.inference_mode(): restored=model(tensor)
            array=restored[0].clamp(0,1).permute(1,2,0).mul(255).round().byte().cpu().numpy()
            result=Image.fromarray(array).resize((picture.width*2,picture.height*2),Image.Resampling.LANCZOS)
            b=io.BytesIO();result.save(b,format='PNG');results[f'{path.stem}-{kind}']=b.getvalue()
            del tensor,restored
            print(f'{path.name} {kind} done',flush=True)
        del model;torch.cuda.empty_cache()
    return results,meta
@app.local_entrypoint()
def main():
    p=ROOT/'outputs/verification/detail-restormer';p.mkdir(parents=True,exist_ok=True)
    images,meta=compare.remote()
    for name,data in images.items():(p/f'{name}.png').write_bytes(data)
    (p/'models.json').write_text(json.dumps(meta,indent=2))
