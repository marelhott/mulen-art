"""User-approved two-folder corpus. All 247 sources, no aesthetic exclusion."""
import hashlib, io, json
from pathlib import Path
from PIL import Image, ImageCms, ImageOps
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/research/tuymans'
ALLOWED={Path('/Users/mulenmara/Pictures/TUY resized-images'),Path('/Users/mulenmara/Pictures/Tuymans hi-res')}
def main():
    rows=json.loads((OUT/'approved-sources-inventory.json').read_text())['images']
    captions={int(line.split('|',1)[0]):line.split('|',1)[1] for line in (ROOT/'training/approved_captions.txt').read_text().splitlines() if line.strip()}
    assert len(rows)==247 and set(captions)==set(range(247))
    dest=OUT/'dataset-approved-v3'
    if dest.exists(): raise RuntimeError('Refusing to overwrite a prepared dataset')
    whole=dest/'whole';detail=dest/'detail';whole.mkdir(parents=True);detail.mkdir()
    manifest=[]
    for i,r in enumerate(rows):
        source=Path(r['path'])
        if source.parent not in ALLOWED: raise ValueError('Unapproved source')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Source changed')
        with Image.open(source) as raw:
            software=str(raw.getexif().get(305,''))
            im=ImageOps.exif_transpose(raw);icc=im.info.get('icc_profile')
            if icc:im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile('sRGB'),outputMode='RGB')
            else:im=im.convert('RGB')
            topaz='topaz' in software.lower() or source.parent.name=='Tuymans hi-res'
            record={**r,'index':i,'software':software,'topaz_processed':topaz,'caption':'mvhpaint, '+captions[i],'split':'train','detail_crops':[]}
            # Never amplify enhanced detail by making close crops from Topaz sources.
            if not topaz and min(im.size)>=1024:
                x=(im.width-1024)//2;y=(im.height-1024)//2
                name=f'detail_{i:03d}'
                im.crop((x,y,x+1024,y+1024)).save(detail/(name+'.png'))
                (detail/(name+'.txt')).write_text('mvhpaint\n')
                record['detail_crops'].append({'file':name+'.png','box':[x,y,x+1024,y+1024],'caption':'mvhpaint','reason':'Native 1024px center detail; style-only caption avoids assigning off-crop subjects'})
            im.thumbnail((2048,2048),Image.Resampling.LANCZOS)
            name=f'whole_{i:03d}';im.save(whole/(name+'.png'));(whole/(name+'.txt')).write_text(record['caption']+'\n')
            record['prepared_size']=im.size;manifest.append(record)
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    summary={'whole_sources':len(manifest),'detail_crops':sum(len(r['detail_crops']) for r in manifest),'topaz_sources':sum(r['topaz_processed'] for r in manifest),'all_sources_in_training':True,'held_out_artworks':0,'validation':'Novel input photographs; cannot assert held-out artwork generalization','cfg':.5,'denoise':[.50,.55],'steps':28,'positive_prompt':'','generic_replay':False,'note':'247 files are not 247 verified distinct artworks. Duplicate reproductions retained transparently; no aesthetic filtering.'}
    (dest/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (dest/'POPiSKY_KONTROLA.md').write_text('# Všech 247 schválených zdrojů\n\nPouze dvě složky potvrzené uživatelem. Celé reprodukce včetně kreseb a grafických motivů; žádný estetický výběr. Popisky vycházejí z vizuálního přehledu, nejsou ověřenými názvy děl. Výřezy pouze z nezvětšených zdrojů s alespoň 1024 px na kratší straně.\n\n'+'\n'.join(f"- {r['index']:03d}: {r['caption']} | Topaz: {r['topaz_processed']} | {Path(r['path']).name}" for r in manifest))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
