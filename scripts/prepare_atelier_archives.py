"""Prepare private, proportion-preserving reference copies; never train weights."""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image, ImageOps


def prepare(sources, destination):
    destination.mkdir(parents=True, exist_ok=True)
    archives, audit = [], []
    for archive_id, name, folders in sources:
        items = []
        for folder in folders:
            for source in sorted(folder.iterdir()):
                if not source.is_file() or source.name.startswith('.') or source.suffix.lower() in {'.txt', '.json', '.csv', '.md', '.zip'}:
                    continue
                try:
                    original = source.read_bytes()
                    digest = hashlib.sha256(original).hexdigest()
                    with Image.open(source) as raw:
                        image = ImageOps.exif_transpose(raw).convert('RGB')
                    original_size = image.size
                    image.thumbnail((1536,1536), Image.Resampling.LANCZOS)
                    relative = f'{archive_id}/{digest}.png'
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    image.save(target, 'PNG')
                    items.append({'id':f'{archive_id}-{len(items)+1:04}', 'filename':source.name,
                        'path':relative, 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                        'original_sha256':digest, 'original_width':original_size[0],
                        'original_height':original_size[1], 'width':image.width,'height':image.height})
                    audit.append({'source':str(source),'archive':archive_id,'status':'ready','size':original_size})
                except Exception as exc:
                    audit.append({'source':str(source),'archive':archive_id,'status':'failed','error':str(exc)})
        archives.append({'id':archive_id,'name':name,'count':len(items),'items':items})
    (destination/'manifest.json').write_text(json.dumps({'version':1,'archives':archives},ensure_ascii=False,indent=2))
    return audit


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sources=[('hofmann','Julius Hofmann',[Path('/Users/mulenmara/Pictures/Julius Hofmann - Photos originals')]),
        ('tuymans','Luc Tuymans',[Path('/Users/mulenmara/Pictures/TUY resized-images'),Path('/Users/mulenmara/Pictures/Tuymans hi-res')])]
    audit=prepare(sources,args.output)
    (args.output.parent/'archive-import-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    from collections import Counter
    print(Counter((x['archive'],x['status']) for x in audit))
