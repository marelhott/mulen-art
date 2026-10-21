"""Add the artist's own paintings (prepared training dataset) to the private reference archives as "mulen".

They then serve as colour source for the Mulen Mara checkpoint and as an "Archiv -> fúze" reference.
Usage: .venv/bin/python scripts/add_mulen_archive.py   (needs outputs/research/mulen_mara/dataset-mulen-v1)
Uploads to the img2img-archives Volume under atelier-archives/mulen and merges the remote manifest.
"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'outputs/research/mulen_mara/dataset-mulen-v1'
PY = [sys.executable, '-m', 'modal']


def modal(*args):
    return subprocess.run([*PY, *args], capture_output=True, text=True, check=True, cwd=ROOT).stdout


def main():
    rows = [r for r in json.loads((DATASET / 'manifest.json').read_text()) if r['used']]
    assert len(rows) == 226
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / 'mulen'
        stage.mkdir()
        items = []
        for row in rows:
            with Image.open(DATASET / 'whole' / row['prepared']) as image:
                image = image.convert('RGB')
                image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
                target = stage / (row['sha256'] + '.png')
                image.save(target, 'PNG')
                items.append({'id': f'mulen-{len(items) + 1:04}', 'filename': row['file'], 'path': f'mulen/{row["sha256"]}.png',
                              'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'original_sha256': row['sha256'],
                              'original_width': row['original_size'][0], 'original_height': row['original_size'][1],
                              'width': image.width, 'height': image.height})
        remote = Path(tmp) / 'manifest.json'
        modal('volume', 'get', 'img2img-archives', 'atelier-archives/manifest.json', str(remote), '--force')
        manifest = json.loads(remote.read_text())
        manifest['archives'] = [a for a in manifest['archives'] if a['id'] != 'mulen'] + [
            {'id': 'mulen', 'name': 'Mulen Mara', 'count': len(items), 'items': items}]
        remote.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        modal('volume', 'put', 'img2img-archives', str(stage), 'atelier-archives/mulen', '--force')
        modal('volume', 'put', 'img2img-archives', str(remote), 'atelier-archives/manifest.json', '--force')
    print(f'added {len(items)} paintings; archives now: {[a["id"] for a in manifest["archives"]]}')


if __name__ == '__main__':
    main()
