"""One bounded Modal GPU smoke test for the optional production Real-SR GAN path."""
import io
import time
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("img2img-realsrgan-smoke")
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install_from_requirements(str(ROOT / "app_runtime/requirements.txt"))
         .add_local_python_source("app_runtime")
         .add_local_dir(str(ROOT / "outputs/verification/sr-patches"), "/patches"))


@app.function(image=image, gpu=["L4", "A10G"], timeout=300, max_containers=1, retries=0)
def smoke():
    from PIL import Image
    from app_runtime.realsrgan import upscale
    start = time.monotonic()
    source = Image.open("/patches/canvas.png").convert("RGB")
    result = upscale(source)
    buffer = io.BytesIO()
    result.save(buffer, format="PNG")
    return buffer.getvalue(), source.size, result.size, round(time.monotonic() - start, 2)


@app.local_entrypoint()
def main():
    data, source_size, output_size, seconds = smoke.remote()
    target = ROOT / "outputs/verification/detail-sr/production-realsrgan-smoke.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print({"source": source_size, "output": output_size, "seconds": seconds, "saved": str(target)})
