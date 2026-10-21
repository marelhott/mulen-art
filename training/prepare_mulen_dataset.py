"""Mulen Mara corpus: the artist's own paintings from ~/Desktop/moje obrazy -> private training dataset.

Captions are keyed by FILENAME (never by position). Rules, all derived from the Tuymans v3 policy:
  * EXIF orientation applied, embedded ICC converted to sRGB;
  * Lanczos downscale to at most 2048 px on the long side, never upscaled, no sharpening;
  * no detail crops (225 of the 228 files went through Topaz Photo AI, so native crops would teach its artifacts);
  * two near-identical pairs are reduced to the less processed file (recorded in the manifest).
"""
import hashlib, io, json
from pathlib import Path
from PIL import Image, ImageCms, ImageOps

Image.MAX_IMAGE_PIXELS = None  # own trusted files, some above 400 MP; scoped to this script only
ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/mulenmara/Desktop/moje obrazy')
OUT = ROOT / 'outputs/research/mulen_mara/dataset-mulen-v1'
TRIGGER = 'mulpaint'
MAX_SIDE = 2048
# Near-identical pairs (mean grey difference < 4/255 at 32x32); keep the file with less AI processing.
DROPPED = {
    'Gesture (Frenhofer)  80x60-topaz-enhance-2x-sharpen.jpeg': 'near-duplicate of the denoise version (kept)',
    'Nilon-topaz-enhance-6x-sharpen.jpeg': 'near-duplicate of the sharpen-only version (kept); 6x AI enlargement',
}


def main():
    captions = {}
    for line in (ROOT / 'training/mulen_mara_captions.txt').read_text(encoding='utf-8').splitlines():
        name, caption = line.split('|', 1)
        captions[name] = caption.strip()
    files = sorted((p for p in SOURCE.glob('*.jpeg')), key=lambda p: p.name.lower())
    assert len(files) == 228 and {p.name for p in files} == set(captions), 'captions must match the 228 files by name'
    assert set(DROPPED) <= set(captions)
    if OUT.exists():
        raise RuntimeError('Refusing to overwrite a prepared dataset')
    whole = OUT / 'whole'; whole.mkdir(parents=True)
    manifest = []
    for p in files:
        if p.name in DROPPED:
            manifest.append({'file': p.name, 'used': False, 'reason': DROPPED[p.name]}); continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        with Image.open(p) as raw:
            software = str(raw.getexif().get(305, ''))
            im = ImageOps.exif_transpose(raw)
            icc = im.info.get('icc_profile')
            if icc:
                im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
            else:
                im = im.convert('RGB')
            original = im.size
            if max(im.size) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            index = len(manifest)
            name = f'whole_{index:03d}'
            im.save(whole / (name + '.png'))
            caption = f'{TRIGGER}, {captions[p.name]}'
            (whole / (name + '.txt')).write_text(caption + '\n', encoding='utf-8')
            manifest.append({'file': p.name, 'used': True, 'sha256': digest, 'prepared': name + '.png', 'original_size': list(original),
                             'prepared_size': list(im.size), 'software': software, 'icc_converted': bool(icc), 'caption': caption})
    used = [m for m in manifest if m['used']]
    assert len(used) == 226
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'sources': 228, 'used': len(used), 'dropped': DROPPED, 'trigger': TRIGGER, 'max_side': MAX_SIDE,
               'detail_crops': 0, 'held_out_artworks': 0, 'topaz_processed': sum('topaz' in m['software'].lower() for m in used),
               'note': 'Downscaling the Topaz-processed originals (median 4236 px short side) to <=2048 px averages out most generated micro-texture.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
