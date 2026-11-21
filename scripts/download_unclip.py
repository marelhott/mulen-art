"""Download Stable Diffusion 2.1 unCLIP (the model behind Clipdrop's old "Reimagine") into Modal storage.

Stability AI removed stabilityai/stable-diffusion-2-1-unclip from Hugging Face in Nov 2025; this
pulls the fp16 diffusers files from the sd2-community mirror at a pinned revision (~3.9 GiB),
verifies SHA-256 of every weight file, and commits them to /models/unclip on the models Volume.

Run: .venv/bin/python -m modal run scripts/download_unclip.py
"""
import modal

app = modal.App("img2img-unclip-download")
volume = modal.Volume.from_name("img2img-models")
image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx==0.28.1")

REPO = "sd2-community/stable-diffusion-2-1-unclip"
REVISION = "ac4aaff4a67d57bdab2e9faf277c33d8e49f4df4"
TARGET = "/models/unclip"
# path -> sha256 (None for small config/tokenizer files, which are size-checked by transfer only)
FILES = {
    "model_index.json": None,
    "feature_extractor/preprocessor_config.json": None,
    "image_noising_scheduler/scheduler_config.json": None,
    "scheduler/scheduler_config.json": None,
    "tokenizer/merges.txt": None,
    "tokenizer/special_tokens_map.json": None,
    "tokenizer/tokenizer_config.json": None,
    "tokenizer/vocab.json": None,
    "image_encoder/config.json": None,
    "image_normalizer/config.json": None,
    "text_encoder/config.json": None,
    "unet/config.json": None,
    "vae/config.json": None,
    "image_encoder/model.fp16.safetensors": "64a7ef761bfccbadbaa3da77366aac4185a6c58fa5de5f589b42a65bcc21f161",
    "image_normalizer/diffusion_pytorch_model.fp16.safetensors": "532a80f90c5602b0f76f557b01417afc5b438598e0f02459ae4c254f5755ad74",
    "text_encoder/model.fp16.safetensors": "6ab158327d06ce861b5c78843672c78433ea82fcf03f142097ba204b81251cd2",
    "unet/diffusion_pytorch_model.fp16.safetensors": "a11c42f0619d06677f792a29b36277bf78bcefb7c010583c631da62e40630ff5",
    "vae/diffusion_pytorch_model.fp16.safetensors": "c8b011e5a18c53888d51a81aa28223ddec87b450c14dc9650d9c3ebbcd17624e",
}


@app.function(image=image, volumes={"/models": volume}, cpu=2, memory=2048, timeout=3600)
def download():
    import hashlib
    import httpx
    from pathlib import Path
    volume.reload()
    done, fetched = 0, 0
    for name, expected in FILES.items():
        path = Path(TARGET) / name
        if path.exists():
            if expected is None:
                done += 1
                continue
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                    done += 1
                    continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".download")
        digest = hashlib.sha256()
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
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
    return f"unCLIP ready in {TARGET}: {fetched} downloaded, {done} already present"


@app.local_entrypoint()
def main():
    print(download.remote())
