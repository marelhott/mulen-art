"""Optional fast migration from existing public R2 copies, verified against local files.

Run: .venv/bin/python -m modal run scripts/import_models.py
"""
import hashlib
import base64
import struct
import json
from pathlib import Path
import modal

app = modal.App("img2img-model-import")
volume = modal.Volume.from_name("img2img-models", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx==0.28.1")

@app.function(image=image, volumes={"/models": volume}, cpu=2, memory=2048, timeout=1800)
def import_verified(manifest: list[dict]):
    import concurrent.futures
    import httpx
    import os

    def fetch(item):
        destination = Path("/models") / item["destination"].lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.stat().st_size == item["size"]:
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]:
                    print(f"Verified existing: {destination.name}", flush=True)
                    return destination.name
        temporary = destination.with_suffix(".download")
        digest = hashlib.sha256()
        count = 0
        last_report = 0
        print(f"Downloading {destination.name}", flush=True)
        try:
            with httpx.stream("GET", item["url"], timeout=httpx.Timeout(60, read=120), follow_redirects=True) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    # Local files have edited metadata headers. Preserve them byte for
                    # byte and stream the tensor payload from the existing R2 copy.
                    chunks = response.iter_bytes(8 * 1024 * 1024)
                    first = next(chunks)
                    remote_header_size = struct.unpack("<Q", first[:8])[0]
                    if remote_header_size + 8 > len(first):
                        raise ValueError("Remote safetensors header exceeds first chunk")
                    local_prefix = base64.b64decode(item["prefix_base64"])
                    output.write(local_prefix)
                    digest.update(local_prefix)
                    count = len(local_prefix)
                    from itertools import chain
                    for chunk in chain([first[8 + remote_header_size:]], chunks):
                        output.write(chunk)
                        digest.update(chunk)
                        count += len(chunk)
                        if count - last_report >= 512 * 1024 * 1024:
                            last_report = count
                            print(f"{destination.name}: {count / item['size']:.0%}", flush=True)
            if count != item["size"] or digest.hexdigest() != item["sha256"]:
                raise ValueError(f"Local/cloud file mismatch: {destination.name}; refusing to use it")
            os.replace(temporary, destination)
            print(f"SHA-256 verified: {destination.name} ({count} bytes)", flush=True)
            return destination.name
        finally:
            temporary.unlink(missing_ok=True)

    volume.reload()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(fetch, manifest))
    volume.commit()
    return verified

@app.local_entrypoint()
def main():
    root = Path(__file__).resolve().parents[1]
    source = Path("/Users/mulenmara/CODE_DISK/models")
    config = json.loads((root / "config/models.json").read_text())
    manifest = []
    for section in ("models", "loras"):
        for item in config[section]:
            if item.get("kind") == "base" or item.get("origin") == "modal-training":
                continue
            if not item.get("path"):
                continue
            name = Path(item["path"]).name
            folder = "checkpoints" if section == "models" else "lora"
            local = source / folder / name
            print(f"Hashing local {name}", flush=True)
            with local.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                stream.seek(0)
                header_size = struct.unpack("<Q", stream.read(8))[0]
                stream.seek(0)
                prefix = stream.read(8 + header_size)
            base = ("https://pub-4e46dcff44d744a1a90ab901a1cc9db5.r2.dev/checkpoints" if section == "models"
                    else "https://pub-1694387d01ff49229be71d63751ffd94.r2.dev/loras")
            manifest.append({"url": f"{base}/{name}", "destination": item["path"].removeprefix("/models"),
                             "size": local.stat().st_size, "sha256": digest,
                             "prefix_base64": base64.b64encode(prefix).decode()})
    report = root / "outputs" / "verification" / "model-manifest.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(manifest, indent=2))
    verified = import_verified.remote(manifest)
    print(f"Verified and committed {len(verified)} model files.")
