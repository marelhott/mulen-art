"""Matched-size crops and descriptive consistency checks, not perceptual quality scores."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter,ImageDraw

root=Path(__file__).resolve().parents[1]/'outputs/verification'
folder=root/'detail-sr'
metrics={}
for name in ['canvas','atelier']:
    source=Image.open(root/'sr-inputs'/f'{name}.png').convert('RGB')
    sr=Image.open(folder/f'{name}-swinir.png').convert('RGB')
    baseline=source.resize(sr.size,Image.Resampling.LANCZOS)
    sharp=baseline.filter(ImageFilter.UnsharpMask(radius=.6,percent=45,threshold=3))
    blend=Image.fromarray(np.rint(.5*np.asarray(baseline,dtype=float)+.5*np.asarray(sr,dtype=float)).clip(0,255).astype('uint8'))
    variants={'Lanczos':baseline,'Current gentle sharpen':sharp,'SwinIR reconstruction':sr,'SwinIR 50 percent':blend}
    sheet=Image.new('RGB',(384*4,424*2),'#222');draw=ImageDraw.Draw(sheet)
    width,height=sr.size
    centers=[(.28,.58),(.65,.40)] if name=='canvas' else [(.5,.5),(.16,.32)]
    src=np.asarray(source,dtype=np.float32)
    metrics[name]={}
    for column,(label,picture) in enumerate(variants.items()):
        for row,(cx,cy) in enumerate(centers):
            x=max(0,min(width-384,int(width*cx)-192));y=max(0,min(height-384,int(height*cy)-192))
            sheet.paste(picture.crop((x,y,x+384,y+384)),(384*column,424*row+32))
            draw.text((384*column+8,424*row+8),label,fill='white')
        picture.save(folder/f'{name}-{column}.png')
        roundtrip=np.asarray(picture.resize(source.size,Image.Resampling.LANCZOS),dtype=np.float32)
        low=np.asarray(picture.filter(ImageFilter.GaussianBlur(8)),dtype=np.float32)
        lowbase=np.asarray(baseline.filter(ImageFilter.GaussianBlur(8)),dtype=np.float32)
        metrics[name][label]={'downscale_mae_0_255':float(np.abs(roundtrip-src).mean()),
                              'low_frequency_change_0_255':float(np.abs(low-lowbase).mean())}
    sheet.save(folder/f'{name}-comparison.png')
(folder/'metrics.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics,indent=2))
