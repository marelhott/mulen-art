"""Copy a finished training checkpoint into the app's model Volume entirely on Modal (nothing passes through the Mac).

Usage: .venv/bin/python -m modal run scripts/install_checkpoint.py --run RUN_ID --source mulen_mara_full_unet.safetensors --name mulen_mara
The copy is verified by SHA-256 of source and destination, and by reading the safetensors header.
"""
import modal

app = modal.App('mulen-install-checkpoint')
results = modal.Volume.from_name('mulen-training-results')
models = modal.Volume.from_name('img2img-models')
image = modal.Image.debian_slim(python_version='3.11').pip_install('safetensors==0.4.5')


@app.function(image=image, volumes={'/results': results, '/models': models}, cpu=2, memory=4096, timeout=3600)
def install(run: str, source: str, name: str):
    import hashlib, json, shutil, struct
    from pathlib import Path
    if '/' in run or '..' in run or '/' in source or '/' in name:
        raise ValueError('Invalid path component')
    results.reload()
    src = Path('/results') / run / source
    dst = Path('/models/checkpoints') / f'{name}.safetensors'
    if not src.is_file():
        raise FileNotFoundError(src)
    if dst.exists():
        raise RuntimeError(f'{dst} already exists; refusing to overwrite')

    def sha(path):
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1 << 24), b''):
                digest.update(block)
        return digest.hexdigest()

    with src.open('rb') as handle:  # safetensors header: 8-byte length + JSON listing every tensor
        header = json.loads(handle.read(struct.unpack('<Q', handle.read(8))[0]))
    tensors = {k: v for k, v in header.items() if k != '__metadata__'}
    shutil.copyfile(src, dst)
    models.commit()
    source_hash, dest_hash = sha(src), sha(dst)
    if source_hash != dest_hash:
        raise RuntimeError('Checksum mismatch after copy')
    dtypes = sorted({v['dtype'] for v in tensors.values()})
    return {'destination': str(dst), 'bytes': dst.stat().st_size, 'sha256': dest_hash, 'tensors': len(tensors), 'dtypes': dtypes}


@app.local_entrypoint()
def main(run: str, source: str = 'mulen_mara_full_unet.safetensors', name: str = 'mulen_mara'):
    import json
    print(json.dumps(install.remote(run, source, name), indent=2))
