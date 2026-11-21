"""Download the SDXL IP-Adapters (ViT-H, plain and plus) and their image encoder into Modal storage.

Used by the unCLIP tab's "Metamorfóza" mode (SDXL Base img2img conditioned on the source picture).
Pinned revision of h94/IP-Adapter, SHA-256 verified, ~4.1 GiB, written to /models/ipadapter.

Run: .venv/bin/python -m modal run scripts/download_ipadapter.py
"""
import modal

app = modal.App("img2img-ipadapter-download")
volume = modal.Volume.from_name("img2img-models")
image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx==0.28.1")

REPO = "h94/IP-Adapter"
REVISION = "018e402774aeeddd60609b4ecdb7e298259dc729"
TARGET = "/models/ipadapter"
FILES = {
    "models/image_encoder/config.json": None,
    "models/image_encoder/model.safetensors": "6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030",
    "sdxl_models/ip-adapter_sdxl_vit-h.safetensors": "ebf05d918348aec7abb02a5e9ecef77e0aaea6914a5c4ea13f50d45eb1681831",
    "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors": "3f5062b8400c94b7159665b21ba5c62acdcd7682262743d7f2aefedef00e6581",
}


@app.function(image=image, volumes={"/models": volume}, cpu=2, memory=2048, timeout=3600)
def download():
    import hashlib
    import httpx
    from pathlib import Path
    volume.reload()
    fetched, present = 0, 0
    for name, expected in FILES.items():
        path = Path(TARGET) / name
        if path.exists():
            if expected is None:
                present += 1
                continue
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                    present += 1
                    continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".download")
        digest = hashlib.sha256()
        try:
            with httpx.stream("GET", f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}", follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes(8 * 1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
            if expected is not None and digest.hexdigest() != expected:
                raise ValueError(f"SHA-256 mismatch for {name}; refusing file")
            temporary.replace(path)
            fetched += 1
            print(f"ok {name}", flush=True)
        finally:
            temporary.unlink(missing_ok=True)
    volume.commit()
    return f"IP-Adapter ready in {TARGET}: {fetched} downloaded, {present} already present"


@app.local_entrypoint()
def main():
    print(download.remote())
