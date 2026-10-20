"""Download the official SDXL Canny ControlNet directly into Modal storage.

Structure-only guidance: the network receives an edge map, so no source pixels or
palette reach the diffusion latent. Run: .venv/bin/modal run scripts/download_controlnet.py
"""
import modal

app = modal.App("img2img-controlnet-download")
volume = modal.Volume.from_name("img2img-models", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface-hub==0.27.1", "safetensors==0.5.2")
)


@app.function(image=image, volumes={"/models": volume}, cpu=2, memory=4096, timeout=3600)
def download(repo: str, revision: str, destination: str) -> str:
    from pathlib import Path
    from huggingface_hub import snapshot_download

    volume.reload()
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=str(target),
        allow_patterns=["*.json", "*.safetensors", "*.txt"],
        # The TensorFlow/Flax/ONNX variants are not used by this app.
        ignore_patterns=["*.bin", "*.msgpack", "*.h5", "*.onnx", "*tf_model*"],
    )
    weight = target / "diffusion_pytorch_model.fp16.safetensors"
    if not weight.is_file():
        raise RuntimeError(f"Expected fp16 weights were not downloaded into {target}")
    volume.commit()
    return f"{weight} ({weight.stat().st_size} bytes)"


@app.local_entrypoint()
def main() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    entry = next(item for item in json.loads((root / "config/models.json").read_text())["controlnets"] if item["id"] == "canny_sdxl")
    print(download.remote(entry["repo"], entry["revision"], entry["path"]))
