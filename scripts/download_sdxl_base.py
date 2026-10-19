"""Download the official SDXL Base checkpoint directly into Modal storage."""
import modal

app = modal.App("img2img-base-download")
volume = modal.Volume.from_name("img2img-models")
image = modal.Image.debian_slim(python_version="3.11").pip_install("httpx==0.28.1")


@app.function(image=image, volumes={"/models": volume}, cpu=2, memory=2048, timeout=1800)
def download():
    import hashlib
    import httpx
    from pathlib import Path
    expected = "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"
    path = Path("/models/checkpoints/sd_xl_base_1.0.safetensors")
    volume.reload()
    if path.exists():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == expected:
                return "SDXL Base already present; SHA-256 verified"
    temporary = path.with_suffix(".download")
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    url = "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/f298da3c058bd8f1f1c62f3ecfa775244a243897/sd_xl_base_1.0.safetensors"
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(8 * 1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    count += len(chunk)
                    if count % (512 * 1024 * 1024) == 0:
                        print(f"Downloaded {count / 1024**3:.1f} GiB", flush=True)
        if digest.hexdigest() != expected:
            raise ValueError("SDXL SHA-256 mismatch; refusing checkpoint")
        temporary.replace(path)
        volume.commit()
        return f"SDXL Base saved: {count} bytes; SHA-256 verified"
    finally:
        temporary.unlink(missing_ok=True)


@app.local_entrypoint()
def main():
    print(download.remote())
